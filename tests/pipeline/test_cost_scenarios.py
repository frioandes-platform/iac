"""Scenario inputs and wiring, without a pricing API or Azure access."""
from copy import deepcopy
import csv
import json
from io import StringIO
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import yaml

from scripts import infracost_scenarios as scenarios


def effective(config):
    result = deepcopy(config)
    for project in result["projects"]:
        values = {}
        for name in project.pop("terraform_var_files"):
            values.update(json.loads(Path(name).read_text()))
        project["variables"] = values
    return result


class CostScenarioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paths = scenarios.prepare(Path(self.temp.name))
        self.configs = {name: effective(json.loads(path.read_text())) for name, path in self.paths.items()}

    def test_each_scenario_owns_exactly_the_same_four_real_roots(self):
        for config in self.configs.values():
            self.assertEqual([p["name"] for p in config["projects"]], ["connectivity", "dev", "test", "prod"])
            self.assertEqual(len({p["path"] for p in config["projects"]}), 4)
            for project in config["projects"]:
                self.assertEqual(Path(project["path"]), scenarios.ROOT / "environments" / project["name"])
                self.assertEqual(Path(project["usage_file"]), scenarios.ROOT / "infracost-usage.yml")

    def test_capacity_comparison_changes_only_one_terraform_input(self):
        one, two = deepcopy(self.configs["1tu"]), deepcopy(self.configs["2tu"])
        one_ingest = one["projects"][1]["variables"]["ingest"]
        two_ingest = two["projects"][1]["variables"]["ingest"]
        self.assertEqual(one_ingest["capacity"], 1)
        self.assertEqual(two_ingest["capacity"], 2)
        two_ingest["capacity"] = 1
        self.assertEqual(one, two)

    def test_enablement_separately_adds_ingestion_and_shared_dns(self):
        enabled = deepcopy(self.configs["1tu"])
        enabled["projects"][1]["variables"]["ingest"] = None
        enabled["projects"][0]["variables"].update(enable_eventhub_private_dns=False, eventhub_dns_spoke_vnet_ids={})
        self.assertEqual(enabled, self.configs["disabled"])

    def test_shared_dns_ids_and_dev_vnet_reference_are_consistent(self):
        projects = self.configs["1tu"]["projects"]
        connectivity, dev = projects[0]["variables"], projects[1]["variables"]
        self.assertTrue(connectivity["enable_eventhub_private_dns"])
        self.assertEqual(list(connectivity["eventhub_dns_spoke_vnet_ids"]), ["dev"])
        with (scenarios.ROOT / "modules/network/data/ip-plan.csv").open() as stream:
            names = {row["vnet"] for row in csv.DictReader(stream) if row["env"] == "dev"}
        self.assertEqual(names, {connectivity["eventhub_dns_spoke_vnet_ids"]["dev"].rsplit("/", 1)[-1]})
        self.assertIn("/resourceGroups/rg-fa-connectivity/", dev["ingest"]["private_dns_zone_id"])
        self.assertTrue(dev["ingest"]["private_dns_zone_id"].endswith("/privateDnsZones/privatelink.servicebus.windows.net"))

    def test_canonical_estimate_enables_ingestion_and_uses_public_fixtures(self):
        inputs = scenarios.ROOT / "costs/inputs"
        dev = json.loads((inputs / "dev.tfvars.json").read_text())
        self.assertIn("capacity", dev["ingest"])
        self.assertIn("estimate-only", dev["ingest"]["namespace_name"])
        security = json.loads((inputs / "security.tfvars.json").read_text())
        fixture = json.loads((scenarios.ROOT / "tests/fixtures/security-tokens.json").read_text())
        self.assertEqual(security["security_token_values"], fixture)
        self.assertIn("no-desplegar", security["owner_team"])

    def test_usage_does_not_override_terraform_capacity(self):
        usage = yaml.safe_load((scenarios.ROOT / "infracost-usage.yml").read_text())
        namespace = usage["resource_type_default_usage"]["azurerm_eventhub_namespace"]
        self.assertEqual(namespace["monthly_ingress_events"], 1000000)
        self.assertNotIn("throughput_or_capacity_units", namespace)
        self.assertEqual(usage["resource_type_default_usage"]["azurerm_firewall"]["monthly_data_processed_gb"], 18293)

    def test_scenario_changes_trigger_costs_without_changing_pr_comments(self):
        workflow = yaml.load((scenarios.ROOT / ".github/workflows/costs.yml").read_text(), Loader=yaml.BaseLoader)
        for event in ("pull_request", "push"):
            paths = workflow["on"][event]["paths"]
            self.assertIn("costs/**", paths)
            self.assertIn("scripts/infracost_scenarios.py", paths)
        job = workflow["jobs"]["scenarios"]
        self.assertNotIn("permissions", job)
        self.assertTrue(all(step["if"] == "env.INFRACOST_API_KEY != ''" for step in job["steps"][1:]))
        self.assertIn("scripts/infracost_scenarios.py", job["steps"][-1]["run"])

    def test_provenance_hashes_the_actual_terraform_and_estimation_inputs(self):
        record = scenarios.provenance()
        self.assertEqual(len(record["checkout_commit"]), 40)
        self.assertEqual(len(record["input_sha256"]), 64)
        for path in ("modules/ingest/main.tf", "environments/dev/ingest.tf", "costs/inputs/dev.tfvars.json", "infracost-usage.yml"):
            self.assertIn(path, record["file_sha256"])
        self.assertTrue(record["synthetic_inputs_for_estimation_only"])

    def test_a_live_capacity_edit_keeps_controlled_scenarios_and_source_intact(self):
        root = Path(self.temp.name) / "source"
        root.mkdir()
        shutil.copy(scenarios.ROOT / "infracost.yml", root)
        shutil.copytree(scenarios.ROOT / "costs/inputs", root / "costs/inputs")
        source = root / "costs/inputs/dev.tfvars.json"
        values = json.loads(source.read_text())
        values["ingest"]["capacity"] = 2
        source.write_text(json.dumps(values))
        paths = scenarios.prepare(Path(self.temp.name) / "edited", root=root)
        one = effective(json.loads(paths["1tu"].read_text()))
        two = effective(json.loads(paths["2tu"].read_text()))
        self.assertEqual(one["projects"][1]["variables"]["ingest"]["capacity"], 1)
        self.assertEqual(two["projects"][1]["variables"]["ingest"]["capacity"], 2)
        self.assertEqual(json.loads(source.read_text()), values)

    def test_report_shows_comparisons_as_differences_instead_of_new_totals(self):
        record = {key: "test-metadata" for key in ("checkout_commit", "working_tree_dirty", "pull_request_head",
                  "pull_request_base", "run_url", "run_attempt", "input_sha256", "infracost_version")}
        with patch.object(scenarios.subprocess, "check_output", return_value="renderer fixture; not a price") as output:
            scenarios.report(Path(self.temp.name), record, StringIO())
        calls = [call.args[0] for call in output.call_args_list]
        self.assertEqual([next(arg for arg in args if arg.startswith("--format=")) for args in calls],
                         ["--format=table", "--format=table", "--format=diff", "--format=diff"])


if __name__ == "__main__":
    unittest.main()
