"""Driver ordering with fake CLI/cloud responses; these are not Terraform plans."""
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.pipeline import run


class ExecutionTests(unittest.TestCase):
    def exercise(self, reject_gate=None, corrupt_plan=False):
        data = json.loads(run.CONFIG.read_text())
        data["registry"]["login_server"] = "sample.azurecr.io"
        image = "sample.azurecr.io/frioandes/release-probe@sha256:" + "b" * 64
        identity = {"sha": "a" * 40, "run_id": "123", "run_attempt": "1", "image": image}
        previous = {**identity, "environment": "test", "roots": ["test"], "status": "succeeded"}
        calls, outputs, budgets = [], [], []
        gates = 0

        def gate(*args):
            nonlocal gates
            gates += 1
            calls.append("gate")
            budgets.append(args[3])
            if gates == reject_gate:
                raise ValueError("Dispatch window")

        def command(arguments, **kwargs):
            if "show" in arguments:
                return '{"variables":{}}'
            if "apply" in arguments:
                calls.append("apply")
            return ""

        def blob(data, environment, operation, name, path):
            self.assertEqual(operation, "download")
            root = Path(name).stem
            if path.suffix == ".tfplan":
                path.write_bytes(b"synthetic-driver-fixture")
                return
            manifest = {**identity, "environment": "prod", "root": root,
                        "created_at": datetime.now(timezone.utc).isoformat(), "config_sha256": run.digest(run.CONFIG),
                        "lock_sha256": run.digest(run.ROOT / "environments" / root / ".terraform.lock.hcl"),
                        "plan_sha256": run.hashlib.sha256(b"synthetic-driver-fixture").hexdigest()}
            if corrupt_plan:
                manifest["plan_sha256"] = "0" * 64
            path.write_text(json.dumps(manifest))

        failure = None
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"GITHUB_SHA": identity["sha"], "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
                                                       "RELEASE_IMAGE": image, "PREVIOUS_RECEIPT": json.dumps(previous), "INCIDENT_ID": ""}))
            for name in ("protections", "current_main", "login", "registry_login", "image_test", "verify_plan", "summary"):
                stack.enter_context(patch.object(run, name))
            stack.enter_context(patch.object(run, "initialize", return_value=["terraform"]))
            stack.enter_context(patch.object(run, "production_gate", side_effect=gate))
            stack.enter_context(patch.object(run, "command", side_effect=command))
            stack.enter_context(patch.object(run, "blob", side_effect=blob))
            stack.enter_context(patch.object(run, "output", side_effect=lambda key, value: outputs.append((key, value))))
            try:
                run.stage(data, "apply", "prod", Path(temp))
            except ValueError as error:
                failure = error
        self.budgets = budgets
        return calls, outputs, failure

    def test_gate_immediately_precedes_each_shared_and_productive_apply(self):
        calls, outputs, failure = self.exercise()
        self.assertIsNone(failure)
        self.assertEqual(calls, ["gate", "apply", "gate", "apply"])
        receipt = json.loads(outputs[0][1])
        self.assertEqual(receipt["roots"], ["connectivity", "prod"])

    def test_first_production_gate_reserves_time_for_every_remaining_root(self):
        self.exercise()
        self.assertEqual(self.budgets, [2, 1])

    def test_block_after_approval_never_invokes_apply(self):
        calls, outputs, failure = self.exercise(reject_gate=1)
        self.assertIsNotNone(failure)
        self.assertEqual(calls, ["gate"])
        self.assertEqual(outputs, [])

    def test_new_freeze_between_roots_stops_remaining_apply(self):
        calls, outputs, failure = self.exercise(reject_gate=2)
        self.assertIsNotNone(failure)
        self.assertEqual(calls, ["gate", "apply", "gate"])
        self.assertEqual(outputs, [])

    def test_tampered_saved_plan_never_reaches_the_apply_gate(self):
        calls, outputs, failure = self.exercise(corrupt_plan=True)
        self.assertIsNotNone(failure)
        self.assertEqual(calls, [])
        self.assertEqual(outputs, [])


class SecretHandlingTests(unittest.TestCase):
    def test_public_release_identifiers_are_not_marked_as_secret_outputs(self):
        payload = json.dumps({"sha": "a" * 40, "run_id": "123", "registry": "sample.azurecr.io"})
        with patch.object(run, "az", return_value={"value": payload, "id": "version"}), patch.object(run, "mask") as mask:
            value, version = run.secret("vault", "control")
            mask.assert_called_once_with(payload)
            self.assertEqual(value["sha"], "a" * 40)
            self.assertEqual(version, "version")

    def test_registry_login_uses_the_registry_subscription(self):
        data = {"registry": {"name": "sample", "subscription_id": "shared-subscription", "login_server": "sample.azurecr.io"}}
        with patch.object(run, "az", return_value={"accessToken": "short-lived", "loginServer": "sample.azurecr.io"}) as az, \
             patch.object(run, "mask"), patch.object(run, "command"):
            run.registry_login(data)
            self.assertIn("shared-subscription", az.call_args.args)
