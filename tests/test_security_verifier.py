"""Regression tests of the comparator using synthetic records, never Azure plans."""

import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.evaluate_security_contract import firewall_fixture
from scripts.verify_security import DATA, ROOT, compare_firewall, load_sources, resolved


class SecurityVerifierTests(unittest.TestCase):
    def setUp(self):
        _, self.tables = load_sources()
        self.tokens = json.loads((ROOT / "tests/fixtures/security-tokens.json").read_text())
        settings = {r["clave"]: r["valor"] for r in self.tables["firewall-settings.csv"]}
        rules = {}
        groups = {}
        for row in self.tables["firewall-policy.csv"]:
            if not (row["punto_control"] == "azure-firewall" and row["ambiente"] == "dev" and row["vigencia"] == "estable"):
                continue
            group = row["grupo"].split()[0]
            rules[row["id"]] = {
                "group": group, "sources": resolved(row["origen_rangos"], self.tokens),
                "destinations": resolved(row["destino_rangos"], self.tokens),
                "ports": row["puertos"].split(), "protocols": row["protocolo"].split(),
                "kind": row["tipo"], "action": "Allow", "temporary": False,
                "application_protocols": [{"type": p.title(), "port": {"HTTP": 80, "HTTPS": 443}[p]} for p in row["protocolo"].split()] if row["tipo"] == "aplicacion" else [],
            }
            groups[group] = {"temporary": False, "name": row["grupo"].replace(" ", "-")}
        self.resources = firewall_fixture({"settings": settings, "rules": rules, "groups": groups})

    def check(self, resources):
        return compare_firewall(resources, self.tables, {"dev"}, set(), self.tokens)

    def find_rule(self, name):
        for res in self.resources:
            if res["type"] == "azurerm_firewall_policy_rule_collection_group":
                for kind in ("network", "application"):
                    for collection in res["values"][kind + "_rule_collection"]:
                        if collection["rule"][0]["name"] == name:
                            return collection
        self.fail(name)

    def test_matching_fixture_and_source_counts(self):
        self.assertEqual(len(self.check(self.resources)), 11)
        self.assertEqual(len(self.tables["firewall-policy.csv"]), 100)

    def test_missing_rule_is_rejected(self):
        group = next(r["values"] for r in self.resources if r["type"] == "azurerm_firewall_policy_rule_collection_group")
        group["network_rule_collection"].pop()
        with self.assertRaisesRegex(ValueError, "IDs differ"):
            self.check(self.resources)

    def test_action_change_is_rejected(self):
        self.find_rule("FW-203")["action"] = "Deny"
        with self.assertRaisesRegex(ValueError, "action differs"):
            self.check(self.resources)

    def test_source_broadening_is_rejected(self):
        self.find_rule("FW-203")["rule"][0]["source_addresses"] = ["*"]
        with self.assertRaisesRegex(ValueError, "sources differ"):
            self.check(self.resources)

    def test_destination_change_is_rejected(self):
        self.find_rule("FW-316")["rule"][0]["destination_addresses"] = ["Internet"]
        with self.assertRaisesRegex(ValueError, "destinations differ"):
            self.check(self.resources)

    def test_http_https_cross_product_is_rejected(self):
        self.find_rule("FW-318")["rule"][0]["protocols"].append({"type": "Https", "port": 80})
        with self.assertRaisesRegex(ValueError, "protocol/port pairs differ"):
            self.check(self.resources)

    def test_snat_change_is_rejected(self):
        self.resources[0]["values"]["private_ip_ranges"] = ["10.0.0.0/8"]
        with self.assertRaisesRegex(ValueError, "SNAT ranges differ"):
            self.check(self.resources)

    def test_lifespan_change_is_rejected(self):
        self.find_rule("FW-203")["name"] = "temporary-FW-203"
        with self.assertRaisesRegex(ValueError, "lifespan"):
            self.check(self.resources)

    def test_modified_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "data"
            shutil.copytree(DATA, folder)
            with (folder / "firewall-policy.csv").open("a") as stream:
                stream.write("\n")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                load_sources(folder)

    def test_network_snapshot_drift_is_rejected(self):
        # A refreshed security snapshot must not silently diverge from #20.
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "data"
            shutil.copytree(DATA, folder)
            plan = folder / "ip-plan.csv"
            content = plan.read_bytes().replace(b"10.103.0.0/21", b"10.120.0.0/21")
            plan.write_bytes(content)
            path = folder / "source.json"
            manifest = json.loads(path.read_text())
            manifest["files"]["ip-plan.csv"]["sha256"] = hashlib.sha256(content).hexdigest()
            manifest["files"]["ip-plan.csv"]["git_blob_sha"] = hashlib.sha1(
                b"blob " + str(len(content)).encode() + b"\0" + content
            ).hexdigest()
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "Network and security address-plan snapshots differ"):
                load_sources(folder)


if __name__ == "__main__":
    unittest.main()
