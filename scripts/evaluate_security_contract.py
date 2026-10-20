#!/usr/bin/env python3
"""Evaluate exact module locals with Terraform Core (no provider), then check the translation.

The resource-shaped records below are fixtures for the independent comparator.
They are NOT Terraform provider plans or evidence of an Azure deployment.
"""

import argparse
import copy
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

if __package__:
    from .verify_security import ROOT, compare_firewall, compare_nsg, load_sources, security_content_hashes
else:
    from verify_security import ROOT, compare_firewall, compare_nsg, load_sources, security_content_hashes


def evaluate(module, inputs, terraform):
    with tempfile.TemporaryDirectory(prefix="fa-security-core-") as directory:
        base = Path(directory)
        shutil.copytree(ROOT / "modules/security/data", base / "data")
        if module == "firewall":
            path = base
            source = ROOT / "modules/security"
            shutil.copyfile(source / "variables.tf", path / "variables.tf")
            expression = "jsonencode({rules=local.resolved,groups=local.groups,settings=local.settings,unresolved=local.unresolved_tokens})"
        else:
            path = base / "subnet-controls"
            path.mkdir()
            source = ROOT / "modules/security/subnet-controls"
            expression = "jsonencode({rules=local.expanded_rules,subnets=local.subnet_names,unresolved=local.unresolved})"
        # Preserve the exact variable/locals HCL, excluding provider resources.
        (path / "main.tf").write_text((source / "main.tf").read_text().split('resource "', 1)[0])
        (path / "inputs.tfvars.json").write_text(json.dumps(inputs))
        result = subprocess.run([terraform, "console", "-no-color", "-var-file=inputs.tfvars.json"], cwd=path, input=expression + "\n", text=True, capture_output=True)
        if result.returncode:
            raise ValueError(result.stderr)
        return json.loads(json.loads(result.stdout))


def firewall_fixture(core):
    settings = core["settings"]
    resources = [
        {"type": "azurerm_firewall_policy", "values": {
            "sku": settings["sku_tier"], "threat_intelligence_mode": "Deny",
            "private_ip_ranges": settings["snat_private_ranges"].split(),
            "dns": [{"proxy_enabled": False}],
        }},
        {"type": "azurerm_firewall", "values": {
            "sku_tier": settings["sku_tier"],
            "ip_configuration": [{}] * int(settings["public_ip_count"]),
            "management_ip_configuration": [{}],
        }},
    ]
    for key, info in core["groups"].items():
        group = {"name": ("temporary-" if info["temporary"] else "stable-") + info["name"], "priority": int(key), "network_rule_collection": [], "application_rule_collection": []}
        for rid, rule in core["rules"].items():
            if rule["group"] != key:
                continue
            actual = {"name": rid, "source_addresses": rule["sources"], "description": ("TEMPORARY; retire: " + rule["retirement"]) if rule["temporary"] else "STABLE;"}
            kind = "network" if rule["kind"] == "red" else "application"
            if kind == "network":
                actual.update(destination_addresses=rule["destinations"], destination_ports=rule["ports"], protocols=rule["protocols"])
            else:
                actual.update(destination_fqdns=rule["destinations"], protocols=rule["application_protocols"], terminate_tls=False)
            group[kind + "_rule_collection"].append({"name": ("temporary-" if rule["temporary"] else "stable-") + rid, "priority": int(rid.split("-")[1]), "action": rule["action"], "rule": [actual]})
        resources.append({"type": "azurerm_firewall_policy_rule_collection_group", "values": group})
    return resources


def nsg_fixture(core, environment):
    resources = []
    for name in core["subnets"]:
        resources.extend([
            {"type": "azurerm_network_security_group", "values": {"name": f"nsg-fa-{environment}-{name}"}},
            {"type": "azurerm_subnet_network_security_group_association", "values": {}},
        ])
    for rule in core["rules"].values():
        resources.append({"type": "azurerm_network_security_rule", "values": {
            "name": ("temporary-" if rule["temporary"] else "stable-") + rule["id"],
            "description": "TEMPORARY;" if rule["temporary"] else "STABLE;",
            "network_security_group_name": f"nsg-fa-{environment}-{rule['subnet']}",
            "direction": rule["direction"], "access": rule["action"], "protocol": rule["protocol"],
            "priority": rule["priority"], "source_port_range": "*",
            "source_address_prefixes": rule["sources"], "destination_address_prefixes": rule["destinations"],
            "destination_port_ranges": rule["ports"],
        }})
    return resources


def run(terraform):
    _, tables = load_sources()
    tokens = json.loads((ROOT / "tests/fixtures/security-tokens.json").read_text())
    results = []
    firewall_inputs = {
        "resource_group_name": "mock-rg", "location": "eastus2", "tags": {},
        "firewall_subnet_id": "/mock/subnet", "management_subnet_id": "/mock/management",
        "token_values": tokens,
    }
    for name, envs, temporary in [
        ("development_stable_policy", ["dev"], []),
        ("all_environments_stable_policy", ["dev", "test", "prod"], []),
        ("migration_explicitly_selected", ["dev", "test", "prod"], ["FW-401", "FW-402", "FW-501", "FW-502", "FW-503", "FW-504"]),
    ]:
        inputs = dict(firewall_inputs, environments=envs, active_temporary_rule_ids=temporary, migration_change_reference="MOCK-ONLY" if temporary else "")
        core = evaluate("firewall", inputs, terraform)
        assert not core["unresolved"]
        resources = firewall_fixture(core)
        ids = compare_firewall(resources, tables, set(envs), set(temporary), tokens)
        results.append({"case": name, "explicit_source_ids": len(ids), "core_evaluation": "PASS", "provider_plan": False})
    for env in ("dev", "test", "prod"):
        temporaries = [row["id"] for row in tables["firewall-policy.csv"] if row["punto_control"] == "nsg" and row["ambiente"] == env and row["vigencia"] == "temporal"]
        for active in ([[], temporaries] if temporaries else [[]]):
            inputs = {"environment": env, "resource_group_name": "mock-rg", "location": "eastus2", "tags": {}, "subnet_ids": {row["subnet"]: "/mock/" + row["subnet"] for row in tables["ip-plan.csv"] if row["env"] == env}, "token_values": tokens, "active_temporary_rule_ids": active, "migration_change_reference": "MOCK-ONLY" if active else ""}
            core = evaluate("nsg", inputs, terraform)
            ids = compare_nsg(nsg_fixture(core, env), tables, env, set(active), tokens)
            results.append({"case": env + ("_nsg_migration" if active else "_nsg_stable"), "explicit_source_ids": len(ids), "expanded_rules": len(core["rules"]), "core_evaluation": "PASS", "provider_plan": False})
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terraform", default="terraform")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    results = run(args.terraform)
    text = json.dumps({"evidence_type": "Terraform Core evaluation plus synthetic comparator fixtures; NOT provider plans", "code_hashes": security_content_hashes(), "results": results}, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
    print(text)
