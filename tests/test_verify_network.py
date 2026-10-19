"""Negative cases for the independent address and Terraform plan verifier."""

import copy
import csv
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.verify_network import DATA, compare_plan, load_snapshot, validate_addresses
from scripts.prepare_network_data import normalize_plan


class NetworkVerificationTests(unittest.TestCase):
    def setUp(self):
        self.rows, self.onprem = load_snapshot()

    def test_approved_snapshot(self):
        self.assertEqual(validate_addresses(self.rows, self.onprem), (3, 33))

    def test_strict_csv_preserves_all_network_fields(self):
        original = (DATA / "ip-plan.csv").read_bytes()
        raw = list(csv.reader(io.StringIO(original.decode("utf-8"))))
        fixed = list(csv.reader(io.StringIO(normalize_plan(original).decode("utf-8")), strict=True))
        self.assertEqual(sum(len(row) != 10 for row in raw), 3)
        self.assertTrue(all(len(row) == 10 for row in fixed))
        self.assertEqual([row[:9] for row in raw], [row[:9] for row in fixed])
        self.assertEqual(fixed[11][9], ",".join(raw[11][9:]))

    def test_malformed_derived_csv_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "data"
            shutil.copytree(DATA, dest)
            path = dest / "ip-plan.terraform.csv"
            path.write_text(path.read_text().replace("snet-ingress,", "snet-ingress,unexpected,", 1))
            with self.assertRaisesRegex(ValueError, "Normalized CSV differs"):
                load_snapshot(dest)

    def test_modified_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "data"
            shutil.copytree(DATA, dest)
            with (dest / "ip-plan.csv").open("a") as stream:
                stream.write("\n")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                load_snapshot(dest)

    def test_overlapping_subnets_are_rejected(self):
        rows = copy.deepcopy(self.rows)
        dev = [row for row in rows if row["env"] == "dev"]
        dev[1]["cidr"] = dev[0]["cidr"]
        with self.assertRaisesRegex(ValueError, "subnets overlap"):
            validate_addresses(rows, self.onprem)

    def test_onprem_overlap_is_rejected(self):
        onprem = copy.deepcopy(self.onprem)
        onprem[0]["cidr"] = next(row["cidr"] for row in self.rows if row["env"] == "prod")
        with self.assertRaisesRegex(ValueError, "on-premises overlap"):
            validate_addresses(self.rows, onprem)

    def test_plan_must_match_the_entire_environment(self):
        # Synthetic fixture to test the verifier; this is not Terraform execution evidence.
        for env in ("dev", "test", "prod"):
            rows = [row for row in self.rows if row["env"] == env]
            resources = [{"type": "azurerm_virtual_network", "values": {
                "name": rows[0]["vnet"], "address_space": [rows[0]["vnet_cidr"]],
            }}]
            resources.extend({"type": "azurerm_subnet", "values": {
                "name": row["subnet"], "virtual_network_name": row["vnet"], "address_prefixes": [row["cidr"]],
            }} for row in rows)
            plan = {"planned_values": {"root_module": {"child_modules": [{"resources": resources}]}}}
            compare_plan(plan, self.rows, env)
            resources[-1]["values"]["address_prefixes"] = ["192.0.2.0/27"]
            with self.assertRaisesRegex(ValueError, "subnets/CIDRs"):
                compare_plan(plan, self.rows, env)
            resources.pop()
            with self.assertRaisesRegex(ValueError, "subnets/CIDRs"):
                compare_plan(plan, self.rows, env)
            with self.assertRaisesRegex(ValueError, "VNets/CIDRs"):
                compare_plan(plan, self.rows, "prod" if env != "prod" else "dev")


if __name__ == "__main__":
    unittest.main()
