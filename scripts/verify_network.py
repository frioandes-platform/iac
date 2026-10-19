#!/usr/bin/env python3
"""Verify snapshot provenance, address safety, and optionally one Terraform JSON plan."""

import argparse
import csv
import hashlib
import io
import ipaddress
import itertools
import json
from pathlib import Path

if __package__:
    from .prepare_network_data import normalize_plan
else:
    from prepare_network_data import normalize_plan

DATA = Path(__file__).resolve().parents[1] / "modules/network/data"
ENVIRONMENTS = ("dev", "test", "prod")
REQUIRED_CATEGORIES = {
    "ingreso", "aplicacion", "datos", "archivo", "ingesta",
    "administracion", "integracion-cali", "salida-fabric",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_snapshot(data_dir=DATA):
    manifest = json.loads((data_dir / "source.json").read_text(encoding="utf-8"))
    tables = {}
    for name in ("ip-plan.csv", "onprem-inventory.csv"):
        content = (data_dir / name).read_bytes()
        source = manifest["files"][name]
        require(hashlib.sha256(content).hexdigest() == source["sha256"], f"SHA-256 mismatch: {name}")
        blob = b"blob " + str(len(content)).encode() + b"\0" + content
        require(hashlib.sha1(blob).hexdigest() == source["git_blob_sha"], f"Git blob mismatch: {name}")
        if name == "ip-plan.csv":
            normalized = (data_dir / "ip-plan.terraform.csv").read_bytes()
            require(normalized == normalize_plan(content), "Normalized CSV differs from its documented source transformation")
            expected_hash = manifest["derived"]["ip-plan.terraform.csv"]["sha256"]
            require(hashlib.sha256(normalized).hexdigest() == expected_hash, "Normalized CSV checksum mismatch")
            content = normalized
        records = list(csv.reader(io.StringIO(content.decode("utf-8")), strict=True))
        require(all(len(row) == len(records[0]) for row in records), f"Wrong CSV field count: {name}")
        tables[name] = [dict(zip(records[0], row)) for row in records[1:]]
    return tables["ip-plan.csv"], tables["onprem-inventory.csv"]


def validate_addresses(rows, onprem):
    onprem_networks = [ipaddress.ip_network(row["cidr"]) for row in onprem]
    require(len(onprem_networks) == 23, "Review the expected on-premises inventory size.")
    all_subnets, vnets = [], []
    for env in ENVIRONMENTS:
        selected = [row for row in rows if row["env"] == env]
        networks = {(row["vnet"], row["vnet_cidr"]) for row in selected}
        require(len(networks) == 1, f"{env}: expected one VNet")
        require(len(selected) == len({row["subnet"] for row in selected}), f"{env}: duplicate subnet name")
        require(REQUIRED_CATEGORIES <= {row["category"] for row in selected}, f"{env}: missing subnet categories")
        _, cidr = next(iter(networks))
        vnet = ipaddress.ip_network(cidr)
        vnets.append(vnet)
        for row in selected:
            subnet = ipaddress.ip_network(row["cidr"])
            require(subnet.subnet_of(vnet), f"{env}/{row['subnet']}: outside VNet")
            require(not any(subnet.overlaps(other) for other in onprem_networks), f"{env}/{row['subnet']}: on-premises overlap")
            all_subnets.append(subnet)
    for left, right in itertools.combinations(vnets, 2):
        require(not left.overlaps(right), "Application VNets overlap")
    for left, right in itertools.combinations(all_subnets, 2):
        require(not left.overlaps(right), "Application subnets overlap")
    reserved = [ipaddress.ip_network(row["cidr"]) for row in rows if row["env"] in ("hub", "reserva")]
    for vnet in vnets:
        require(not any(vnet.overlaps(other) for other in reserved + onprem_networks), "VNet overlaps hub, reservation, or on-premises network")
    return len(vnets), len(all_subnets)


def iter_resources(module):
    yield from module.get("resources", [])
    for child in module.get("child_modules", []):
        yield from iter_resources(child)


def compare_plan(plan, rows, environment):
    require(environment in ENVIRONMENTS, "Select dev, test, or prod")
    selected = [row for row in rows if row["env"] == environment]
    expected_vnets = {row["vnet"]: [row["vnet_cidr"]] for row in selected}
    expected_subnets = {(row["vnet"], row["subnet"]): [row["cidr"]] for row in selected}
    vnets, subnets = {}, {}
    for resource in iter_resources(plan["planned_values"]["root_module"]):
        if resource.get("mode", "managed") != "managed":
            continue
        value = resource.get("values", {})
        if resource["type"] == "azurerm_virtual_network":
            require(value["name"] not in vnets, "Duplicate planned VNet")
            vnets[value["name"]] = value.get("address_space")
        elif resource["type"] == "azurerm_subnet":
            key = (value["virtual_network_name"], value["name"])
            require(key not in subnets, "Duplicate planned subnet")
            subnets[key] = value.get("address_prefixes")
    require(vnets == expected_vnets, f"{environment}: planned VNets/CIDRs do not exactly match the snapshot")
    require(subnets == expected_subnets, f"{environment}: planned subnets/CIDRs do not exactly match the snapshot")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-json", type=Path)
    parser.add_argument("--environment", choices=ENVIRONMENTS)
    args = parser.parse_args()
    if bool(args.plan_json) != bool(args.environment):
        parser.error("--plan-json and --environment must be provided together")
    try:
        rows, onprem = load_snapshot()
        vnets, subnets = validate_addresses(rows, onprem)
        print(f"PASS: snapshot hashes; {vnets} application VNets, {subnets} subnets; no overlap with 23 on-premises subnets, hub or reservations.")
        if args.plan_json:
            compare_plan(json.loads(args.plan_json.read_text(encoding="utf-8")), rows, args.environment)
            print(f"PASS: {args.environment} Terraform plan exactly matches the approved network names and CIDRs.")
        else:
            print("No Terraform plan supplied; this checks source data, not deployed resources or a Terraform evaluation.")
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f"FAIL: {error}\n")


if __name__ == "__main__":
    main()
