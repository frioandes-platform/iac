#!/usr/bin/env python3
"""Price real Terraform roots with explicit synthetic inputs; never deploy them."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ("disabled", "1tu", "2tu")


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")
    return path


def prepare(destination, root=ROOT):
    """Clone the canonical four-project config; vary only explicit tfvars."""
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    config = yaml.safe_load((root / "infracost.yml").read_text())
    projects = config["projects"]
    if sorted(p["name"] for p in projects) != ["connectivity", "dev", "prod", "test"]:
        raise ValueError("Expected exactly one project per existing Terraform root")
    for project in projects:
        directory = (root / project["path"]).resolve()
        project["terraform_var_files"] = [str((directory / name).resolve()) for name in project["terraform_var_files"]]
        project["path"] = str(directory)
        project["usage_file"] = str((root / project["usage_file"]).resolve())

    inputs = root / "costs/inputs"
    dev = json.loads((inputs / "dev.tfvars.json").read_text())
    connectivity = json.loads((inputs / "connectivity.tfvars.json").read_text())
    configs = {}
    for scenario in SCENARIOS:
        settings = deepcopy(config)
        dev_vars, dns_vars = deepcopy(dev), deepcopy(connectivity)
        if scenario == "disabled":
            dev_vars["ingest"] = None
            dns_vars.update(enable_eventhub_private_dns=False, eventhub_dns_spoke_vnet_ids={})
        else:
            dev_vars["ingest"]["capacity"] = 1 if scenario == "1tu" else 2
        for name, values in (("dev", dev_vars), ("connectivity", dns_vars)):
            variable_file = write_json(destination / f"{scenario}-{name}.tfvars.json", values)
            project = next(p for p in settings["projects"] if p["name"] == name)
            original = str((inputs / f"{name}.tfvars.json").resolve())
            if project["terraform_var_files"].count(original) != 1:
                raise ValueError(f"Expected one explicit estimation input for {name}")
            project["terraform_var_files"] = [str(variable_file) if p == original else p for p in project["terraform_var_files"]]
        # JSON is valid YAML, the configuration format accepted by Infracost.
        configs[scenario] = write_json(destination / f"{scenario}.yml", settings)
    return configs


def provenance(root=ROOT):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

    sources = [root / name for name in ("infracost.yml", "infracost-usage.yml", "scripts/infracost_scenarios.py")]
    sources += list((root / "costs/inputs").glob("*.tfvars.json"))
    for directory in ("environments", "modules"):
        sources += [p for p in (root / directory).rglob("*") if p.is_file() and ".terraform" not in p.parts
                    and (p.suffix == ".tf" or p.name == ".terraform.lock.hcl")]
    hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(sources)}
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    event = json.loads(Path(event_path).read_text()) if event_path else {}
    pr = event.get("pull_request", {})
    repository, run_id = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_RUN_ID")
    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "checkout_commit": git("rev-parse", "HEAD"),
        "working_tree_dirty": bool(git("status", "--porcelain")),
        "pull_request_head": pr.get("head", {}).get("sha"),
        "pull_request_base": pr.get("base", {}).get("sha"),
        "run_url": f"https://github.com/{repository}/actions/runs/{run_id}" if repository and run_id else None,
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "input_sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
        "file_sha256": hashes,
        "synthetic_inputs_for_estimation_only": True,
    }


def price(configs, destination, root=ROOT):
    for scenario, config in configs.items():
        subprocess.run(["infracost", "breakdown", f"--config-file={config}", "--format=json",
                        f"--out-file={destination / (scenario + '.json')}"], cwd=root, check=True)
    for name, before, after in (("enablement", "disabled", "1tu"), ("capacity", "1tu", "2tu")):
        subprocess.run(["infracost", "diff", f"--config-file={configs[after]}",
                        f"--compare-to={destination / (before + '.json')}", "--format=json",
                        f"--out-file={destination / (name + '-diff.json')}"], cwd=root, check=True)


def report(destination, record, stream):
    print("## Ingestion cost scenarios (synthetic estimation inputs)", file=stream)
    print(f"\nCheckout: `{record['checkout_commit']}`; dirty: `{record['working_tree_dirty']}`.", file=stream)
    print(f"Head: `{record['pull_request_head']}`; base: `{record['pull_request_base']}`.", file=stream)
    print(f"Run: {record['run_url']}; attempt: `{record['run_attempt']}`.", file=stream)
    print(f"Inputs SHA-256: `{record['input_sha256']}`. {record['infracost_version']}", file=stream)
    for name, output_format, title in (("1tu", "table", "Ingestion enabled, 1 TU"), ("2tu", "table", "Ingestion enabled, 2 TUs"),
                        ("enablement-diff", "diff", "Enablement: disabled → 1 TU (includes shared DNS and private endpoint)"),
                        ("capacity-diff", "diff", "Capacity only: 1 → 2 TUs (all other inputs identical)")):
        result = subprocess.check_output(["infracost", "output", f"--path={destination / (name + '.json')}",
                                          f"--format={output_format}", "--show-skipped"], cwd=ROOT, text=True)
        print(f"\n### {title}\n\n```text\n{result.rstrip()}\n```", file=stream)
    print("\nUnpriced/skipped resources and missing usage are not zero-cost guarantees. No Azure deployment was performed.", file=stream)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True, help="Use a temporary directory outside the repository")
    parser.add_argument("--prepare-only", action="store_true", help="Generate inputs/configs without querying any prices")
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    configs = prepare(destination)
    record = provenance()
    record["status"] = "prepared-only; no price query"
    write_json(destination / "provenance.json", record)
    if args.prepare_only:
        print(f"Prepared disabled, 1tu and 2tu configs in {destination}; no price query was made.")
        return
    record["infracost_version"] = subprocess.check_output(["infracost", "--version"], text=True).strip()
    record["status"] = "pricing started; results incomplete"
    write_json(destination / "provenance.json", record)
    price(configs, destination)
    record["status"] = "all three breakdowns and both comparisons completed"
    write_json(destination / "provenance.json", record)
    with (destination / "summary.md").open("w") as stream:
        report(destination, record, stream)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
            stream.write((destination / "summary.md").read_text())
    print(f"Real Infracost results, summary and provenance written to {destination}.")


if __name__ == "__main__":
    main()
