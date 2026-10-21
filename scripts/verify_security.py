#!/usr/bin/env python3
"""Independently compare Terraform planned security resources against the pinned CSV."""

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "modules/security/data"


def security_content_hashes():
    """Hash code and fixtures without recording credentials, state or plan contents."""
    result = {}
    for folder in ("modules", "environments", "scripts", "tests"):
        for path in sorted((ROOT / folder).rglob("*")):
            if not path.is_file() or any(part in (".terraform", "__pycache__") for part in path.parts):
                continue
            if path.suffix not in (".tf", ".hcl", ".csv", ".py", ".json"):
                continue
            if path.name.endswith((".tfvars.json", ".tfstate")):
                continue
            result[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_sources(data=DATA):
    manifest = json.loads((data / "source.json").read_text())
    tables = {}
    for name, expected in manifest["files"].items():
        content = (data / name).read_bytes()
        require(hashlib.sha256(content).hexdigest() == expected["sha256"], f"{name}: checksum mismatch")
        require(hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest() == expected["git_blob_sha"], f"{name}: Git blob mismatch")
        lines = list(csv.reader(content.decode().splitlines(), strict=True))
        require(all(len(row) == len(lines[0]) for row in lines), f"{name}: invalid CSV field count")
        tables[name] = [dict(zip(lines[0], row)) for row in lines[1:]]
    rows = tables["firewall-policy.csv"]
    require(len(rows) == len({row["id"] for row in rows}), "Duplicate source rule IDs")
    for row in rows:
        require(row["vigencia"] in ("estable", "temporal"), f"{row['id']}: unknown lifespan")
        require(bool(row["se_retira"]) == (row["vigencia"] == "temporal"), f"{row['id']}: missing or unexpected retirement")
    network_data = ROOT / "modules/network/data"
    network_manifest = json.loads((network_data / "source.json").read_text())
    require(
        network_manifest["files"]["ip-plan.csv"]["sha256"] == manifest["files"]["ip-plan.csv"]["sha256"]
        and (network_data / "ip-plan.csv").read_bytes() == (data / "ip-plan.csv").read_bytes(),
        "Network and security address-plan snapshots differ; reconcile #20 and #21 before planning",
    )
    return manifest, tables


def walk_resources(module):
    yield from module.get("resources", [])
    for child in module.get("child_modules", []):
        yield from walk_resources(child)


def resources_from_plan(plan):
    if "planned_values" in plan:
        return list(walk_resources(plan["planned_values"].get("root_module", {})))
    # terraform test -json -verbose exposes the actual planned resource changes.
    if "resource_changes" in plan:
        return [dict(change, values=change["change"]["after"]) for change in plan["resource_changes"] if change.get("mode", "managed") == "managed" and change["change"].get("after") is not None]
    raise ValueError("Expected Terraform plan JSON or a verbose test_plan event")


def read_plans(path):
    text = Path(path).read_text()
    try:
        plan = json.loads(text)
        if "planned_values" in plan or "resource_changes" in plan:
            return [("plan", plan)]
    except json.JSONDecodeError:
        pass
    result = []
    for line in text.splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("type") == "test_plan":
            result.append((event.get("@testrun", str(len(result))), event["test_plan"]))
    require(bool(result), "No verbose Terraform plan events found")
    return result


def resolved(field, values):
    result = []
    for token in field.split():
        replacement = values.get(token)
        if replacement is None:
            replacement = [token.removeprefix("fqdn:").removeprefix("tag:")]
        result.extend("*" if value == "any" else "Internet" if value == "internet" else value for value in replacement)
    require(all("<" not in value and ">" not in value for value in result), f"Unresolved design token: {field}")
    return sorted(result)


def compare_firewall(resources, tables, environments, active_temporaries, tokens):
    rows = [row for row in tables["firewall-policy.csv"] if row["punto_control"] == "azure-firewall" and row["id"] != "FW-999" and (row["ambiente"] in environments or row["ambiente"] == "hub")]
    allowed_temporary = {row["id"] for row in rows if row["vigencia"] == "temporal"}
    require(set(active_temporaries) <= allowed_temporary, "Temporary IDs outside the selected firewall scope")
    expected = {row["id"]: row for row in rows if row["vigencia"] == "estable" or row["id"] in active_temporaries}
    actual = {}
    policies = [r["values"] for r in resources if r["type"] == "azurerm_firewall_policy"]
    firewalls = [r["values"] for r in resources if r["type"] == "azurerm_firewall"]
    require(len(policies) == len(firewalls) == 1, "Exactly one shared policy and firewall are required")
    require(not any(r["type"] in ("azurerm_firewall_network_rule_collection", "azurerm_firewall_application_rule_collection", "azurerm_firewall_nat_rule_collection") for r in resources), "Unexpected classic firewall collections outside the policy")
    for resource in resources:
        if resource["type"] != "azurerm_firewall_policy_rule_collection_group":
            continue
        group = resource["values"]
        require(not group.get("nat_rule_collection"), "Unexpected DNAT collection")
        for kind in ("network", "application"):
            for collection in group.get(f"{kind}_rule_collection", []) or []:
                for rule in collection.get("rule", []):
                    key = rule["name"]
                    require(key not in actual, f"Duplicate actual firewall rule {key}")
                    actual[key] = (kind, group, collection, rule)
    require(set(actual) == set(expected), f"Firewall IDs differ: missing={sorted(set(expected)-set(actual))}; extra={sorted(set(actual)-set(expected))}")
    for key, row in expected.items():
        kind, group, collection, rule = actual[key]
        require(kind == ("network" if row["tipo"] == "red" else "application"), f"{key}: wrong rule type")
        require(group["priority"] == int(row["grupo"].split()[0]), f"{key}: wrong group priority")
        require(collection["priority"] == int(key.split("-")[1]), f"{key}: wrong collection priority")
        require(collection["action"] == ("Allow" if row["accion"] == "Permitir" else "Deny"), f"{key}: action differs")
        require(sorted(rule["source_addresses"]) == resolved(row["origen_rangos"], tokens), f"{key}: sources differ")
        require(not rule.get("source_ip_groups"), f"{key}: unexpected extra source IP groups")
        destination_key = "destination_addresses" if kind == "network" else "destination_fqdns"
        require(sorted(rule[destination_key]) == resolved(row["destino_rangos"], tokens), f"{key}: destinations differ")
        if kind == "network":
            require(not rule.get("destination_ip_groups") and not rule.get("destination_fqdns"), f"{key}: unexpected extra network destinations")
            require(sorted(rule["destination_ports"]) == resolved(row["puertos"], tokens), f"{key}: ports differ")
            require(sorted(rule["protocols"]) == sorted(row["protocolo"].split()), f"{key}: protocols differ")
        else:
            require(not rule.get("destination_addresses") and not rule.get("destination_urls") and not rule.get("destination_fqdn_tags"), f"{key}: unexpected extra application destinations")
            protocols = sorted((p["type"].lower(), p["port"]) for p in rule["protocols"])
            # Pair by protocol semantics independently of the module's HCL locals.
            expected_protocols = sorted((p.lower(), {"HTTP": 80, "HTTPS": 443}[p]) for p in row["protocolo"].split())
            require(protocols == expected_protocols, f"{key}: protocol/port pairs differ")
            require(sorted({str(p[1]) for p in protocols}) == sorted(set(row["puertos"].split())), f"{key}: source CSV port set differs")
            require(not rule.get("terminate_tls"), f"{key}: unexpected TLS termination")
        temporary = row["vigencia"] == "temporal"
        prefix = "temporary-" if temporary else "stable-"
        require(collection["name"] == prefix + key, f"{key}: lifespan is not explicit")
        require(group["name"] == prefix + row["grupo"].replace(" ", "-"), f"{key}: group name/lifespan differs")
        require(rule.get("description", "").startswith("TEMPORARY; retire: " + row["se_retira"][:30] if temporary else "STABLE;"), f"{key}: lifespan/retirement description differs")
    settings = {row["clave"]: row["valor"] for row in tables["firewall-settings.csv"]}
    policy, firewall = policies[0], firewalls[0]
    require(policy["sku"] == firewall["sku_tier"] == settings["sku_tier"], "Firewall SKU differs")
    require(not policy.get("base_policy_id") and not policy.get("threat_intelligence_allowlist"), "Unexpected inherited policy or threat-intelligence exceptions")
    require(policy["threat_intelligence_mode"] == "Deny", "Threat intelligence differs")
    require(sorted(policy["private_ip_ranges"]) == sorted(settings["snat_private_ranges"].split()), "SNAT ranges differ")
    require(policy["dns"][0]["proxy_enabled"] is False, "DNS proxy differs")
    require(len(firewall["ip_configuration"]) == int(settings["public_ip_count"]), "Egress public-IP count differs")
    require(len(firewall.get("management_ip_configuration", [])) == 1, "Management NIC missing")
    require("FW-999" not in actual, "A catch-all network deny would shadow application rules")
    return sorted(expected)


def compare_nsg(resources, tables, environment, active_temporaries, tokens):
    rows = [row for row in tables["firewall-policy.csv"] if row["punto_control"] == "nsg" and row["ambiente"] == environment]
    expected = {}
    subnet_names = {row["subnet"] for row in tables["ip-plan.csv"] if row["env"] == environment}
    for row in rows:
        if row["vigencia"] == "temporal" and row["id"] not in active_temporaries:
            continue
        names = subnet_names if row["grupo"] == "nsg todas las subredes" else {row["grupo"].removeprefix("nsg ")}
        for subnet in names:
            expected[(row["id"], subnet)] = row
    actual = {}
    associations = [r for r in resources if r["type"] == "azurerm_subnet_network_security_group_association"]
    nsgs = [r for r in resources if r["type"] == "azurerm_network_security_group"]
    require(len(associations) == len(nsgs) == len(subnet_names), f"{environment}: not all subnets have NSG resources/associations")
    require({r["values"]["name"] for r in nsgs} == {f"nsg-fa-{environment}-{name}" for name in subnet_names}, f"{environment}: NSG names differ")
    for nsg in nsgs:
        name = nsg["values"]["name"]
        subnet = name.removeprefix(f"nsg-fa-{environment}-")
        expected_names = {
            ("temporary-" if row["vigencia"] == "temporal" else "stable-") + row["id"]
            for (rule_id, subnet_name), row in expected.items() if subnet_name == subnet
        }
        # The provider can read standalone rules back into this computed field.
        # Do not reject those legitimate duplicates, but reject unknown rules.
        require(all(rule["name"] in expected_names for rule in nsg["values"].get("security_rule", []) or []), f"{environment}: unexpected additional NSG rules")
    for resource in resources:
        if resource["type"] != "azurerm_network_security_rule":
            continue
        rule = resource["values"]
        key_id = rule["name"].removeprefix("stable-").removeprefix("temporary-")
        subnet = rule["network_security_group_name"].removeprefix(f"nsg-fa-{environment}-")
        key = (key_id, subnet)
        require(key not in actual, f"Duplicate NSG rule {key}")
        actual[key] = rule
    require(set(actual) == set(expected), f"{environment}: NSG ID/subnet set differs")
    for key, row in expected.items():
        rule = actual[key]
        require(rule["access"] == ("Allow" if row["accion"] == "Permitir" else "Deny"), f"{key}: NSG action differs")
        for prefix, field in (("source", "origen_rangos"), ("destination", "destino_rangos")):
            values = rule.get(prefix + "_address_prefixes") or [rule.get(prefix + "_address_prefix")]
            require(sorted(values) == resolved(row[field], tokens), f"{key}: NSG {prefix} differs")
        ports = rule.get("destination_port_ranges") or [rule.get("destination_port_range")]
        require(sorted(ports) == resolved(row["puertos"], tokens), f"{key}: NSG ports differ")
        require(rule["source_port_range"] == "*", f"{key}: source ports differ")
        require(rule["protocol"] == ("*" if row["protocolo"] == "Cualquiera" else row["protocolo"].title()), f"{key}: NSG protocol differs")
        require(rule["direction"] == ("Outbound" if row["tipo"] == "nsg-salida" else "Inbound"), f"{key}: NSG direction differs")
        require(rule["priority"] == (4000 if row["accion"] == "Denegar" else 100 + int(row["id"].split("-")[-1]) * 10), f"{key}: NSG priority differs")
        require(rule["name"].startswith("temporary-" if row["vigencia"] == "temporal" else "stable-"), f"{key}: NSG lifespan differs")
    return sorted({key[0] for key in expected})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--kind", choices=("firewall", "nsg"), required=True)
    parser.add_argument("--environments", nargs="+", choices=("dev", "test", "prod"), default=["dev"])
    parser.add_argument("--temporary", nargs="*", default=[])
    parser.add_argument("--tokens", type=Path, required=True)
    parser.add_argument("--run", help="Select one run from verbose terraform test JSON events")
    args = parser.parse_args()
    try:
        _, tables = load_sources()
        tokens = json.loads(args.tokens.read_text())
        plans = [(name, plan) for name, plan in read_plans(args.plan) if not args.run or name == args.run]
        require(len(plans) == 1, "Select exactly one Terraform plan using --run")
        name, plan = plans[0]
        resources = resources_from_plan(plan)
        if args.kind == "firewall":
            ids = compare_firewall(resources, tables, set(args.environments), set(args.temporary), tokens)
        else:
            require(len(args.environments) == 1, "Select one NSG environment")
            ids = compare_nsg(resources, tables, args.environments[0], set(args.temporary), tokens)
        print(f"PASS: {len(ids)} explicit source rule IDs checked against actual planned resources; sin discrepancias ({name}).")
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"FAIL: {error}\n")


if __name__ == "__main__":
    main()
