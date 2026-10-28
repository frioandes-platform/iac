#!/usr/bin/env python3
"""Trusted-main deployment driver. Secrets and saved plans never enter GitHub artifacts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.pipeline.policy import CHANGE_BUDGET_MINUTES, ROOTS, check_environment, check_plan, check_receipt, require, window_gate

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".github/deployment-config.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mask(value):
    escaped = str(value).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::add-mask::{escaped}", flush=True)


def command(args, *, timeout=300, input_text=None, cwd=ROOT):
    # Do not echo commands, provider errors, stdout or stderr: they can contain inputs.
    result = subprocess.run(args, cwd=cwd, input=input_text, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    require(result.returncode == 0, f"{Path(args[0]).name} failed; inspect with an authorized operator (output withheld)")
    return result.stdout


def az(*args, timeout=300):
    return json.loads(command(["az", *args, "--only-show-errors", "--output", "json"], timeout=timeout) or "null")


def github(path):
    require(os.environ.get("GITHUB_API_URL") == "https://api.github.com", "Only the configured GitHub.com host is supported")
    req = Request("https://api.github.com" + path, headers={
        "Authorization": "Bearer " + os.environ["GH_TOKEN"], "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"})
    with urlopen(req, timeout=30) as response:
        return json.load(response)


def config():
    data = json.loads(CONFIG.read_text())
    require(data.get("schema_version") == 1, "Unknown pipeline configuration schema")
    require(data.get("repository") == "frioandes-platform/iac", "Unexpected target repository")
    require(type(data.get("enabled")) is bool, "Explicit enabled flag is required")
    if not data["enabled"]:
        return data
    guid = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
    require(re.fullmatch(guid, data["tenant_id"]) is not None, "Configure the tenant ID")
    registry = data["registry"]
    for key in ("build_client_id", "subscription_id"):
        require(re.fullmatch(guid, registry[key]) is not None, f"Configure registry {key}")
    require(re.fullmatch(r"[a-z0-9]{5,50}", registry["name"]) is not None, "Invalid registry name")
    require(registry["login_server"] == registry["name"] + ".azurecr.io", "Registry endpoint must match its name")
    require(registry["repository"] == "frioandes/release-probe", "Only the demonstration image repository is configured")
    clients = [registry["build_client_id"]]
    state_addresses = []
    for stage in ROOTS:
        settings = data["stages"][stage]
        for role in ("plan", "apply"):
            value = settings[role + "_client_id"]
            require(re.fullmatch(guid, value) is not None, f"Configure the {stage} {role} identity")
            clients.append(value)
        require(re.fullmatch(r"[a-zA-Z][a-zA-Z0-9-]{1,22}[a-zA-Z0-9]", settings["vault"]) is not None, "Configure a valid Key Vault")
        require(re.fullmatch(r"[a-z0-9]{3,24}", settings["plan_storage_account"]) is not None, "Configure private plan storage")
        require(settings["plan_container"] == "plans-" + stage, "Use a separate plan container per stage")
    require(len(set(clients)) == len(clients), "Build, plan and apply identities must be distinct across stages")
    require(len({data["stages"][x]["vault"] for x in ROOTS}) == 3, "Use separate Key Vaults per environment")
    for root in ("dev", "test", "prod", "connectivity"):
        settings = data["roots"][root]
        require(re.fullmatch(guid, settings["subscription_id"]) is not None, f"Configure the {root} subscription")
        require(re.fullmatch(r"[a-z0-9]{3,24}", settings["state_storage_account"]) is not None, "Configure state storage")
        require(settings["state_container"] == "state-" + root and settings["state_key"] == root + ".tfstate", "Separate state container and key per root required")
        require(settings["tfvars_secret"] == "terraform-" + root, "Unexpected tfvars secret name")
        state_addresses.append((settings["state_storage_account"], settings["state_container"], settings["state_key"]))
    require(len(set(state_addresses)) == 4, "State locations must not overlap")
    require(data["stages"]["prod"]["control_secret"] == "production-change-control", "Unexpected operational-control secret")
    return data


def trusted_context(data):
    require(os.environ.get("GITHUB_REPOSITORY") == data["repository"], "Unexpected workflow repository")
    require(os.environ.get("GITHUB_REF") == "refs/heads/main", "Cloud jobs run only on main")
    require(os.environ.get("GITHUB_EVENT_NAME") in ("push", "workflow_dispatch"), "Untrusted workflow event")
    sha = os.environ["GITHUB_SHA"]
    require(re.fullmatch(r"[0-9a-f]{40}", sha) is not None, "Invalid source commit")
    require(command(["git", "rev-parse", "HEAD"]).strip() == sha, "Checkout must match the triggering commit")
    for key in ("ARM_CLIENT_SECRET", "ARM_ACCESS_KEY", "AZURE_CLIENT_SECRET", "ARM_SAS_TOKEN"):
        require(not os.environ.get(key), "Long-lived Azure credentials must not be configured")
    return sha


def current_main(data, sha):
    require(github(f'/repos/{data["repository"]}/git/ref/heads/main')["object"]["sha"] == sha,
            "A newer main commit exists; restart promotion from current main")


def protections(data, stages):
    for stage in stages:
        path = f'/repos/{data["repository"]}/environments/{stage}'
        check_environment(github(path), github(path + "/deployment-branch-policies?per_page=100"), stage == "prod")


def output(key, value):
    with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
        stream.write(f"{key}={value}\n")


def summary(text):
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
        stream.write(text + "\n")


def login(data, client, subscription):
    # Azure CLI and Terraform both use short-lived GitHub OIDC tokens.
    base = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    separator = "&" if "?" in base else "?"
    request = Request(base + separator + urlencode({"audience": "api://AzureADTokenExchange"}),
                      headers={"Authorization": "Bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]})
    with urlopen(request, timeout=30) as response:
        token = json.load(response)["value"]
    mask(token)
    az("login", "--service-principal", "--username", client, "--tenant", data["tenant_id"], "--federated-token", token)
    az("account", "set", "--subscription", subscription)
    os.environ.update(ARM_CLIENT_ID=client, ARM_TENANT_ID=data["tenant_id"], ARM_SUBSCRIPTION_ID=subscription,
                      ARM_USE_OIDC="true", ARM_USE_AZUREAD="true", ARM_USE_CLI="false", TF_IN_AUTOMATION="true", TF_INPUT="false")


def secret(vault, name):
    record = az("keyvault", "secret", "show", "--vault-name", vault, "--name", name)
    mask(record["value"])
    parsed = json.loads(record["value"])
    # Do not mark public metadata leaves (commit SHA, registry host, run ID)
    # as secrets: GitHub would suppress the promotion outputs containing them.
    # The complete payload is masked and raw CLI/provider output is never logged.
    return parsed, record["id"]


def production_gate(data, identity, incident, remaining_roots=1):
    protections(data, ["prod"])
    current_main(data, identity["sha"])
    settings = data["stages"]["prod"]
    control, version = secret(settings["vault"], settings["control_secret"])
    decision = window_gate(control, datetime.now(timezone.utc), incident,
                           data["repository"], identity["sha"], identity["run_id"], identity["run_attempt"],
                           budget_minutes=CHANGE_BUDGET_MINUTES * remaining_roots)
    # Values are public audit identifiers, never the control document or its secrets.
    summary(f"- Gate: {decision}. Control version: `{version.rsplit('/', 1)[-1]}`.")


def registry_login(data):
    registry = data["registry"]
    token = az("acr", "login", "--name", registry["name"], "--subscription", registry["subscription_id"], "--expose-token")
    require(token["loginServer"] == registry["login_server"], "Unexpected ACR endpoint")
    mask(token["accessToken"])
    command(["docker", "login", registry["login_server"], "--username", "00000000-0000-0000-0000-000000000000",
             "--password-stdin"], input_text=token["accessToken"])


def build_image(sha, tag):
    directory = ROOT / "containers/release-probe"
    build_env = os.environ.copy()
    os.environ.update(CGO_ENABLED="0", GOOS="linux", GOARCH="amd64", GOTOOLCHAIN="local")
    try:
        command(["go", "build", "-trimpath", "-ldflags", f"-s -w -X main.revision={sha}",
                 "-o", str(directory / "release-probe"), str(directory / "main.go")])
    finally:
        os.environ.clear()
        os.environ.update(build_env)
    command(["docker", "build", "--network=none", "--tag", tag, str(directory)])
    image_test(tag)


def image_test(image):
    command(["docker", "run", "--rm", "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", image, "--self-test"])


def blob(data, stage, operation, name, path):
    settings = data["stages"][stage]
    args = ["storage", "blob", operation, "--account-name", settings["plan_storage_account"],
            "--container-name", settings["plan_container"], "--name", name, "--file", str(path), "--auth-mode", "login"]
    if operation == "upload":
        args.extend(["--overwrite", "false"])
    az(*args)


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    path.chmod(0o600)


def initialize(data, root, temporary):
    settings = data["roots"][root]
    os.environ["ARM_SUBSCRIPTION_ID"] = settings["subscription_id"]
    az("account", "set", "--subscription", settings["subscription_id"])
    os.environ["TF_DATA_DIR"] = str(temporary / ("terraform-" + root))
    backend = temporary / (root + ".backend.hcl")
    values = {"storage_account_name": settings["state_storage_account"], "container_name": settings["state_container"],
              "key": settings["state_key"], "use_oidc": True, "use_azuread_auth": True}
    backend.write_text("".join(f"{key} = {json.dumps(value)}\n" for key, value in values.items()))
    tf = ["terraform", f"-chdir={ROOT / 'environments' / root}"]
    command(tf + ["init", "-input=false", "-reconfigure", "-lockfile=readonly", f"-backend-config={backend}"], timeout=600)
    command(tf + ["validate"])
    return tf


def verify_plan(plan, root, inputs):
    from scripts.verify_network import compare_plan, load_snapshot
    from scripts.verify_security import compare_firewall, compare_nsg, load_sources, resources_from_plan
    _, tables = load_sources()
    resources = resources_from_plan(plan)
    tokens = inputs.get("security_token_values", {})
    if root == "connectivity":
        selected = set(inputs.get("protected_environments", ["dev"]))
        require(selected == {"dev", "test", "prod"}, "Shared production firewall must cover all three promoted environments")
        compare_firewall(resources, tables, selected, set(inputs.get("active_temporary_firewall_rules", [])), tokens)
    else:
        rows, _ = load_snapshot()
        compare_plan(plan, rows, root)
        compare_nsg(resources, tables, root, set(inputs.get("active_temporary_nsg_rules", [])), tokens)


def identity(image):
    require(re.fullmatch(r"[a-z0-9]+\.azurecr\.io/frioandes/release-probe@sha256:[0-9a-f]{64}", image) is not None,
            "Promotion requires an immutable ACR image digest")
    return {"sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
            "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"], "image": image}


def stage(data, action, environment, temporary):
    release = identity(os.environ["RELEASE_IMAGE"])
    require(release["image"].startswith(data["registry"]["login_server"] + "/"), "Image registry differs")
    previous = json.loads(os.environ.get("PREVIOUS_RECEIPT") or "{}")
    check_receipt(previous, environment, release)
    protections(data, [environment])
    current_main(data, release["sha"])
    settings = data["stages"][environment]
    login(data, settings[action + "_client_id"], data["roots"][environment]["subscription_id"])
    prefix = f'{release["sha"]}/{release["run_id"]}/{release["run_attempt"]}/{environment}'
    if action == "apply":
        registry_login(data)
        command(["docker", "pull", release["image"]], timeout=600)
        image_test(release["image"])
    roots = ROOTS[environment]
    for index, root in enumerate(roots):
        tf = initialize(data, root, temporary)
        plan_file, manifest_file = temporary / (root + ".tfplan"), temporary / (root + ".json")
        lock_sha = digest(ROOT / "environments" / root / ".terraform.lock.hcl")
        if action == "plan":
            inputs, input_version = secret(settings["vault"], data["roots"][root]["tfvars_secret"])
            require(isinstance(inputs, dict), "Terraform input secret must be a JSON object")
            input_file = temporary / (root + ".tfvars.json")
            write_json(input_file, inputs)
            command(tf + ["plan", "-input=false", "-lock-timeout=60s", f"-var-file={input_file}", f"-out={plan_file}"], timeout=1200)
            plan = json.loads(command(tf + ["show", "-json", str(plan_file)]))
            verify_plan(plan, root, inputs)
            changes = [{"address": x["address"], "actions": x["change"]["actions"]}
                       for x in plan.get("resource_changes", []) if x["change"]["actions"] != ["no-op"]]
            manifest = {**release, "environment": environment, "root": root, "created_at": datetime.now(timezone.utc).isoformat(),
                        "config_sha256": digest(CONFIG), "lock_sha256": lock_sha, "plan_sha256": digest(plan_file),
                        "input_secret_version": input_version, "changes": changes}
            write_json(manifest_file, manifest)
            blob(data, environment, "upload", f"{prefix}/{root}.tfplan", plan_file)
            blob(data, environment, "upload", f"{prefix}/{root}.json", manifest_file)
            summary(f"\n**{root} saved plan** — commit `{release['sha']}`, image `{release['image']}`.\n")
            for change in changes:
                summary(f"- `{change['address']}`: {', '.join(change['actions'])}")
            summary(f"Private review location: `{settings['plan_storage_account']}/{settings['plan_container']}/{prefix}/{root}.tfplan`. No values are published here.")
        else:
            blob(data, environment, "download", f"{prefix}/{root}.json", manifest_file)
            blob(data, environment, "download", f"{prefix}/{root}.tfplan", plan_file)
            manifest = json.loads(manifest_file.read_text())
            check_plan(manifest, release, environment, root, datetime.now(timezone.utc), digest(CONFIG), lock_sha)
            require(digest(plan_file) == manifest["plan_sha256"], "Saved plan checksum differs")
            saved = json.loads(command(tf + ["show", "-json", str(plan_file)]))
            inputs = {key: value["value"] for key, value in saved["variables"].items()}
            verify_plan(saved, root, inputs)
            input_file = temporary / (root + ".tfvars.json")
            write_json(input_file, inputs)
            current_main(data, release["sha"])
            if environment == "prod":
                # Must run AFTER approval and immediately before EACH production mutation.
                # The budget covers this root and every later one, so the clock alone
                # cannot stop prod after connectivity was already applied.
                production_gate(data, release, os.environ.get("INCIDENT_ID", ""), len(roots) - index)
            command(tf + ["apply", "-input=false", "-lock-timeout=60s", str(plan_file)], timeout=1200)
            # Refresh-only plan is read-only and detects drift immediately after apply.
            command(tf + ["plan", "-refresh-only", "-detailed-exitcode", "-input=false", "-lock-timeout=60s", f"-var-file={input_file}"], timeout=300)
            summary(f"- Applied saved plan for `{root}`; post-apply drift check passed.")
    if action == "apply":
        receipt = {**release, "environment": environment, "roots": ROOTS[environment], "status": "succeeded"}
        output("receipt", json.dumps(receipt, separators=(",", ":")))
        summary(f"Promotion succeeded for `{environment}`. This is infrastructure validation and image self-test, not an application end-to-end test.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "build", "plan", "apply", "build-local"))
    parser.add_argument("--environment", choices=tuple(ROOTS))
    args = parser.parse_args()
    os.umask(0o077)
    if args.action == "build-local":
        sha = command(["git", "rev-parse", "HEAD"]).strip()
        build_image(sha, "frioandes-release-probe:local")
        return
    data = config()
    sha = trusted_context(data)
    if args.action == "preflight":
        output("enabled", str(data["enabled"]).lower())
        if data["enabled"]:
            protections(data, tuple(ROOTS))
            current_main(data, sha)
            summary("Cloud prerequisites and GitHub environment protections verified.")
        else:
            summary("Cloud promotion is disabled until Azure bootstrap and protected environments are configured. Validation remains enabled; no deployment is claimed.")
        return
    require(data["enabled"], "Cloud deployment has not been bootstrapped")
    with tempfile.TemporaryDirectory(prefix="fa-pipeline-", dir=os.environ["RUNNER_TEMP"]) as temp:
        temporary = Path(temp)
        os.environ["AZURE_CONFIG_DIR"] = str(temporary / "azure")
        os.environ["DOCKER_CONFIG"] = str(temporary / "docker")
        try:
            if args.action == "build":
                current_main(data, sha)
                registry = data["registry"]
                login(data, registry["build_client_id"], registry["subscription_id"])
                registry_login(data)
                tag = f'{registry["login_server"]}/{registry["repository"]}:sha-{sha}-run-{os.environ["GITHUB_RUN_ID"]}-{os.environ["GITHUB_RUN_ATTEMPT"]}'
                build_image(sha, tag)
                command(["docker", "push", tag], timeout=600)
                details = json.loads(command(["docker", "image", "inspect", tag]))[0]
                images = [x for x in details["RepoDigests"] if x.startswith(registry["login_server"] + "/" + registry["repository"] + "@")]
                require(len(images) == 1, "Expected exactly one immutable published image")
                identity(images[0])
                output("image", images[0])
                summary(f"Built, self-tested and pushed `{images[0]}` once for this promotion.")
            else:
                require(args.environment is not None, "Environment is required")
                stage(data, args.action, args.environment, temporary)
        finally:
            # Ephemeral runners are destroyed after each job, including cancellation.
            subprocess.run(["az", "account", "clear"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired) as error:
        # Do not include potentially sensitive CLI arguments, request URLs or values.
        if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError):
            message = str(error)
        else:
            message = "Pipeline input, tool, API or deadline failure; deployment stopped"
        print(f"::error::{message}", file=sys.stderr)
        sys.exit(1)
