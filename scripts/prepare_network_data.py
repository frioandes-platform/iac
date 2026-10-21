#!/usr/bin/env python3
"""Check strict source CSV and produce a canonical copy for verification."""

import csv
import hashlib
import io
import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "modules/network/data"
HEADER = ["env", "vnet", "vnet_cidr", "subnet", "cidr", "category", "zone", "service", "internet", "notes"]


def normalize_plan(content):
    records = list(csv.reader(io.StringIO(content.decode("utf-8")), strict=True))
    if not records or records[0] != HEADER:
        raise ValueError("Unexpected address-plan header")
    normalized = [HEADER]
    for number, row in enumerate(records[1:], 2):
        if len(row) != len(HEADER):
            raise ValueError(f"Wrong CSV field count on line {number}")
        normalized.append(row)
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(normalized)
    return output.getvalue().encode("utf-8")


def main():
    manifest_path = DATA / "source.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    original = (DATA / "ip-plan.csv").read_bytes()
    if hashlib.sha256(original).hexdigest() != manifest["files"]["ip-plan.csv"]["sha256"]:
        raise SystemExit("FAIL: upstream snapshot checksum changed; review it before normalization")
    normalized = normalize_plan(original)
    (DATA / "ip-plan.terraform.csv").write_bytes(normalized)
    manifest["derived"] = {
        "ip-plan.terraform.csv": {
            "source": "ip-plan.csv",
            "sha256": hashlib.sha256(normalized).hexdigest(),
            "transformation": "Canonical RFC 4180 quoting and LF line endings; reject malformed rows; preserve all ten fields",
        }
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Verified strict source CSV and generated canonical verification copy; all fields preserved.")


if __name__ == "__main__":
    main()
