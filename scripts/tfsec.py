#!/usr/bin/env python3
"""Install and run the pinned tfsec scanner without Azure credentials."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.28.14"
# Official v1.28.14 release checksum file; the extracted binary is pinned too.
ARCHIVE_SHA256 = "329ae7f67f2f1813ebe08de498719ea7003c75d3ca24bb0b038369062508008e"
BINARY_SHA256 = "a32d0799bbefababaa4fcd814da9f4d251cd932789590b99d1d5fcb89ace6f68"
URL = f"https://github.com/aquasecurity/tfsec/releases/download/v{VERSION}/tfsec_{VERSION}_linux_amd64.tar.gz"
BINARY = ROOT / ".tools" / "tfsec" / VERSION / "tfsec"
TARGETS = (
    "modules/network", "modules/security", "modules/security/subnet-controls", "modules/ingest",
    "environments/connectivity", "environments/dev", "environments/test", "environments/prod",
)


def checksum(path, expected):
    actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch: {path}")


def install():
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "amd64"):
        raise ValueError("This pinned installer supports Linux amd64 (Ubuntu and GitHub runners).")
    if BINARY.is_file():
        checksum(BINARY, BINARY_SHA256)
        print(f"tfsec v{VERSION} already installed and verified.", flush=True)
        return
    BINARY.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="install-", dir=BINARY.parent) as temporary:
        archive = Path(temporary) / "tfsec.tar.gz"
        print(f"Downloading official tfsec v{VERSION} release.", flush=True)
        with urllib.request.urlopen(URL, timeout=60) as source, archive.open("wb") as destination:
            shutil.copyfileobj(source, destination)
        checksum(archive, ARCHIVE_SHA256)
        candidate = Path(temporary) / "tfsec"
        with tarfile.open(archive, "r:gz") as bundle:
            member = bundle.getmember("tfsec")
            if not member.isfile():
                raise ValueError("Release binary is not a regular file.")
            with bundle.extractfile(member) as source, candidate.open("wb") as destination:
                shutil.copyfileobj(source, destination)
        checksum(candidate, BINARY_SHA256)
        candidate.chmod(0o755)
        os.replace(candidate, BINARY)
    print(f"Installed verified tfsec v{VERSION}: {BINARY}", flush=True)


def verified_binary():
    if not BINARY.is_file():
        raise ValueError("Run python3 scripts/tfsec.py install first.")
    checksum(BINARY, BINARY_SHA256)
    return BINARY


def scanner_environment():
    # Ambient tfsec flags must not silently weaken the repository's CI checks.
    return {key: value for key, value in os.environ.items() if not key.startswith("TFSEC_")}


def scan():
    binary = verified_binary()
    failures = []
    for target in TARGETS:
        print(f"\n=== tfsec v{VERSION}: {target} ===", flush=True)
        result = subprocess.run(
            [str(binary), str(ROOT / target), "--no-module-downloads", "--no-color"],
            cwd=ROOT, env=scanner_environment(), timeout=300,
        )
        if result.returncode:
            failures.append((target, result.returncode))
    if failures:
        raise ValueError(f"tfsec scan failed: {failures}")
    print(f"PASS: tfsec scanned all {len(TARGETS)} module/environment targets.", flush=True)


PROBE = '''resource "azurerm_network_security_rule" "probe" {
  name                        = "synthetic-ssh-probe"
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "22"
  source_address_prefix       = "SOURCE_RANGE"
  destination_address_prefix  = "*"
  resource_group_name         = "synthetic-only"
  network_security_group_name = "synthetic-only"
}
'''


def detection_test():
    binary = verified_binary()
    with tempfile.TemporaryDirectory(prefix="frioandes-tfsec-probe-") as temporary:
        directory = Path(temporary)
        fixture = directory / "fixture"
        fixture.mkdir()
        outcomes = []
        # These ranges exist only inside a temporary, synthetic rule; never in the address plan.
        for label, source in (("public-ssh", "0.0.0.0/0"), ("restricted-ssh", "10.255.255.0/24")):
            (fixture / "main.tf").write_text(PROBE.replace("SOURCE_RANGE", source))
            report = directory / f"{label}.json"
            result = subprocess.run(
                [str(binary), str(fixture), "--no-module-downloads", "--no-color",
                 "--format", "json", "--out", str(report)],
                cwd=directory, env=scanner_environment(), capture_output=True, text=True, timeout=60,
            )
            if not report.is_file():
                raise ValueError(f"Detection probe produced no report ({label}, exit {result.returncode}).")
            findings = json.loads(report.read_text()).get("results") or []
            outcomes.append((label, result.returncode, findings))
        unsafe, fixed = outcomes
        ids = {row.get("long_id") for row in unsafe[2]}
        expected = "azure-network-ssh-blocked-from-internet"
        if unsafe[1] != 1 or expected not in ids:
            raise ValueError(f"Public SSH was not rejected by the expected check: exit={unsafe[1]}, checks={sorted(str(i) for i in ids)}")
        if fixed[1] != 0 or fixed[2]:
            raise ValueError(f"Restricted synthetic SSH did not pass: exit={fixed[1]}")
    print(f"PASS: public SSH rejected (exit 1; {expected}); restricted rule passed (exit 0).", flush=True)
    print("Temporary fixtures removed; no project Terraform or Azure resources changed.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("install", "scan", "test-detection"))
    args = parser.parse_args()
    try:
        {"install": install, "scan": scan, "test-detection": detection_test}[args.operation]()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
