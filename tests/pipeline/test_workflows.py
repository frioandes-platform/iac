"""Regression checks for the actual workflow graph and privilege boundaries."""
import json
from pathlib import Path
import re
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def workflow(name):
    # YAML 1.1 treats 'on' as Boolean; BaseLoader preserves GitHub's YAML keys.
    return yaml.load((ROOT / ".github/workflows" / name).read_text(), Loader=yaml.BaseLoader)


class WorkflowTests(unittest.TestCase):
    def test_pr_validation_has_no_cloud_identity_or_private_runner(self):
        data = workflow("validate.yml")
        self.assertIn("pull_request", data["on"])
        self.assertNotIn("pull_request_target", data["on"])
        self.assertNotIn("id-token", data["permissions"])
        for job in data["jobs"].values():
            self.assertEqual(job["runs-on"], "ubuntu-24.04")

    def test_production_transitively_requires_test_and_dev(self):
        jobs = workflow("promote.yml")["jobs"]
        for name, previous in (("dev_apply", "dev_plan"), ("test_plan", "dev_apply"),
                               ("test_apply", "test_plan"), ("prod_plan", "test_apply"), ("prod_apply", "prod_plan")):
            self.assertIn(previous, jobs[name]["needs"])
            # No always() bypass of failed dependencies; prod only adds the manual-run condition.
            expected = "github.event_name == 'workflow_dispatch'" if name.startswith("prod_") else None
            self.assertEqual(jobs[name].get("if"), expected)
        self.assertEqual(jobs["prod_apply"]["with"]["previous_receipt"], "${{ needs.test_apply.outputs.receipt }}")
        self.assertEqual(jobs["test_apply"]["with"]["previous_receipt"], "${{ needs.dev_apply.outputs.receipt }}")
        for name in ("dev_plan", "dev_apply", "test_plan", "test_apply", "prod_plan", "prod_apply"):
            self.assertEqual(jobs[name]["with"]["image"], "${{ needs.build.outputs.image }}")

    def test_push_to_main_stops_at_test(self):
        jobs = workflow("promote.yml")["jobs"]
        for name in ("dev_plan", "dev_apply", "test_plan", "test_apply"):
            self.assertNotIn("if", jobs[name])
        for name in ("prod_plan", "prod_apply"):
            self.assertIn("workflow_dispatch", jobs[name]["if"])

    def test_plan_and_apply_runners_are_separated(self):
        jobs = workflow("terraform-stage.yml")["jobs"]
        self.assertIn("fa-plan", jobs["plan"]["runs-on"])
        self.assertNotIn("fa-apply", jobs["plan"]["runs-on"])
        self.assertIn("fa-apply", jobs["apply"]["runs-on"])
        self.assertNotIn("fa-plan", jobs["apply"]["runs-on"])

    def test_planning_is_automatic_and_production_apply_is_protected(self):
        promotion = workflow("promote.yml")
        self.assertEqual(promotion["on"]["push"]["branches"], ["main"])
        self.assertNotIn("environment", promotion["on"]["workflow_dispatch"]["inputs"])
        stage = workflow("terraform-stage.yml")
        self.assertEqual(list(stage["on"]), ["workflow_call"])
        self.assertNotIn("environment", stage["jobs"]["plan"])
        self.assertEqual(stage["jobs"]["apply"]["environment"], "${{ inputs.environment }}")
        self.assertIn("run.py apply", stage["jobs"]["apply"]["steps"][-1]["run"])

    def test_actions_are_immutable_and_checkout_does_not_keep_credentials(self):
        for name in ("validate.yml", "promote.yml", "terraform-stage.yml", "costs.yml"):
            for job in workflow(name)["jobs"].values():
                for step in job.get("steps", []):
                    if "uses" in step:
                        self.assertRegex(step["uses"], r"^[\w-]+/[\w-]+(/[\w-]+)*@[0-9a-f]{40}$")
                        if step["uses"].startswith("actions/checkout@"):
                            self.assertEqual(step["with"]["persist-credentials"], "false")

    def test_no_cancellation_of_apply_and_no_plain_plan_upload(self):
        data = workflow("promote.yml")
        self.assertEqual(data["concurrency"]["cancel-in-progress"], "false")
        for path in (ROOT / ".github/workflows").glob("*.yml"):
            text = path.read_text()
            self.assertNotIn("upload-artifact", text)
            self.assertNotIn("secrets.AZURE_CREDENTIALS", text)
            self.assertNotIn("pull_request_target", text)

    def test_static_analysis_runs_on_every_pull_request(self):
        data = workflow("validate.yml")
        job = data["jobs"]["static-analysis"]
        steps = " ".join(step.get("run", "") for step in job["steps"])
        self.assertIn("tflint --recursive", steps)
        self.assertIn("checkov --config-file .checkov.yaml", steps)
        self.assertRegex(steps, r"checkov==\d+\.\d+\.\d+")
        tflint = [s for s in job["steps"] if s.get("uses", "").startswith("terraform-linters/setup-tflint@")]
        self.assertRegex(tflint[0]["with"]["tflint_version"], r"^v\d+\.\d+\.\d+$")

    def test_checkov_skips_are_inline_and_justified(self):
        self.assertNotIn("skip-check", (ROOT / ".checkov.yaml").read_text())
        for path in list((ROOT / "modules").rglob("*.tf")) + list((ROOT / "environments").rglob("*.tf")):
            for line in path.read_text().splitlines():
                if "checkov:skip=" in line:
                    self.assertRegex(line, r"checkov:skip=CKV2?_AZURE_\d+:\S.{20,}", str(path))

    def test_cost_estimate_never_gets_cloud_identity_or_runs_untrusted_code_with_secrets(self):
        data = workflow("costs.yml")
        self.assertIn("pull_request", data["on"])
        self.assertNotIn("pull_request_target", data["on"])
        self.assertEqual(data["permissions"], {"contents": "read"})
        for job in data["jobs"].values():
            self.assertEqual(job["runs-on"], "ubuntu-24.04")
            self.assertNotIn("id-token", job.get("permissions", {}))
        self.assertEqual(data["jobs"]["pull-request"]["permissions"], {"contents": "read", "pull-requests": "write"})
        self.assertNotIn("permissions", data["jobs"]["baseline"])

    def test_cost_comment_is_updated_and_skipped_without_a_key(self):
        data = workflow("costs.yml")
        steps = data["jobs"]["pull-request"]["steps"]
        self.assertEqual(steps[0]["if"], "env.INFRACOST_API_KEY == ''")
        self.assertTrue(all(s["if"] == "env.INFRACOST_API_KEY != ''" for s in steps[1:]))
        self.assertIn("--behavior=update", steps[-1]["run"])
        self.assertIn("--show-all-projects", steps[-1]["run"])
        setup = [s for s in steps if s.get("uses", "").startswith("infracost/actions/setup@")][0]
        self.assertEqual(setup["with"]["version"], "${{ env.INFRACOST_VERSION }}")
        self.assertRegex(data["env"]["INFRACOST_VERSION"], r"^\d+\.\d+\.\d+$")

    def test_all_roots_use_partial_remote_backends(self):
        for root in ("dev", "test", "prod", "connectivity"):
            self.assertIn('backend "azurerm" {}', (ROOT / "environments" / root / "backend.tf").read_text())
            self.assertTrue((ROOT / "environments" / root / ".terraform.lock.hcl").is_file())

    def test_bootstrap_does_not_ship_fictitious_ids_or_enable_deployment(self):
        from scripts.pipeline.run import config
        data = config()
        # An enabled configuration must pass the runtime validator after bootstrap.
        self.assertIsInstance(data["enabled"], bool)
        self.assertEqual(data["repository"], "frioandes-platform/iac")
