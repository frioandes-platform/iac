"""Boundary and rejection cases for release safety; no Azure deployment."""
import copy
from datetime import datetime, timedelta, timezone
import unittest

from scripts.pipeline.policy import check_environment, check_plan, check_receipt, instant, window_gate

IDENTITY = {"sha": "a" * 40, "run_id": "123", "run_attempt": "1", "image": "registry/image@sha256:" + "b" * 64}


class WindowTests(unittest.TestCase):
    def setUp(self):
        # UTC 03:00 = Colombia 22:00 on the preceding calendar date.
        self.now = instant("2026-10-22T03:00:00Z")
        self.control = {"schema_version": 1, "campaign_active": False, "campaign_windows": [],
                        "issued_at": "2026-10-22T00:00:00Z", "valid_until": "2026-10-23T00:00:00Z", "incidents": []}

    def gate(self, moment=None, incident=""):
        return window_gate(self.control, moment or self.now, incident, "frioandes-platform/iac", "a" * 40, "123", "1")

    def incident(self):
        self.control["incidents"] = [{"id": "INC-123", "status": "declared", "environment": "prod",
            "repository": "frioandes-platform/iac", "sha": "a" * 40, "run_id": "123", "run_attempt": "1",
            "approved_by": "incident-commander", "record_url": "https://github.com/frioandes-platform/planning/issues/100",
            "valid_from": "2026-10-22T00:00:00Z", "valid_until": "2026-10-23T00:00:00Z"}]

    def test_2200_is_open_in_bogota(self):
        self.assertIn("passed", self.gate())

    def test_215959_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "Dispatch"):
            self.gate(self.now - timedelta(seconds=1))

    def test_0400_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "Dispatch"):
            self.gate(instant("2026-10-22T09:00:00Z"))

    def test_032959_has_budget(self):
        self.gate(instant("2026-10-22T08:29:59Z"))

    def test_0330_has_insufficient_budget(self):
        with self.assertRaisesRegex(ValueError, "Insufficient time"):
            self.gate(instant("2026-10-22T08:30:00Z"))

    def test_midnight_is_open(self):
        self.gate(instant("2026-10-22T05:00:00Z"))

    def test_campaign_blocks_even_at_night(self):
        self.control["campaign_active"] = True
        with self.assertRaisesRegex(ValueError, "campaign"):
            self.gate()

    def test_scheduled_campaign_start_inside_change_budget_blocks(self):
        self.control["campaign_windows"] = [{"start": "2026-10-22T03:20:00Z", "end": "2026-10-23T00:00:00Z"}]
        with self.assertRaisesRegex(ValueError, "campaign"):
            self.gate()

    def test_missing_campaign_calendar_blocks(self):
        del self.control["campaign_windows"]
        with self.assertRaises(ValueError):
            self.gate()

    def test_unknown_campaign_status_fails_closed(self):
        for value in (None, "false", 0):
            with self.subTest(value=value):
                self.control["campaign_active"] = value
                with self.assertRaises(ValueError):
                    self.gate()
        del self.control["campaign_active"]
        with self.assertRaises(ValueError):
            self.gate()

    def test_stale_future_and_short_lived_control_block(self):
        for issued, expires in (("2026-10-21T00:00:00Z", "2026-10-22T00:00:00Z"),
                                ("2026-10-22T04:00:00Z", "2026-10-23T00:00:00Z"),
                                ("2026-10-22T00:00:00Z", "2026-10-22T03:29:00Z"),
                                ("2026-10-22T00:00:00Z", "2026-10-24T00:00:00Z")):
            with self.subTest(issued=issued, expires=expires):
                self.control.update(issued_at=issued, valid_until=expires)
                with self.assertRaises(ValueError):
                    self.gate()

    def test_incident_input_alone_is_not_authorization(self):
        with self.assertRaisesRegex(ValueError, "independently authorized"):
            self.gate(incident="INC-123")

    def test_incident_allows_campaign_and_dispatch(self):
        self.incident()
        self.control["campaign_active"] = True
        self.assertIn("Incident exception", self.gate(instant("2026-10-22T12:00:00Z"), "INC-123"))

    def test_incident_is_bound_to_the_release_and_an_approver(self):
        self.incident()
        approved = copy.deepcopy(self.control)
        for key, value in (("sha", "c" * 40), ("run_id", "456"), ("run_attempt", "2"), ("environment", "dev"),
                           ("status", "closed"), ("approved_by", ""), ("record_url", "https://example.test/100"),
                           ("valid_until", "2026-10-22T03:20:00Z")):
            with self.subTest(key=key):
                self.control = copy.deepcopy(approved)
                self.control["incidents"][0][key] = value
                with self.assertRaises(ValueError):
                    self.gate(incident="INC-123")

    def test_timezone_is_not_optional(self):
        with self.assertRaises(ValueError):
            instant("2026-10-22T00:00:00")
        with self.assertRaises(ValueError):
            self.gate(datetime(2026, 10, 22, 3))

    def test_approval_waiting_until_dispatch_does_not_keep_old_permission(self):
        self.gate(instant("2026-10-22T08:00:00Z"))
        with self.assertRaises(ValueError):
            self.gate(instant("2026-10-22T09:00:00Z"))


class PromotionTests(unittest.TestCase):
    def receipt(self, environment):
        return {**IDENTITY, "environment": environment, "status": "succeeded", "roots": [environment]}

    def test_ordered_chain(self):
        check_receipt({}, "dev", IDENTITY)
        check_receipt(self.receipt("dev"), "test", IDENTITY)
        check_receipt(self.receipt("test"), "prod", IDENTITY)

    def test_cannot_skip_test(self):
        with self.assertRaises(ValueError):
            check_receipt(self.receipt("dev"), "prod", IDENTITY)

    def test_failed_missing_or_incomplete_predecessor_is_rejected(self):
        for receipt in ({}, {**self.receipt("test"), "status": "failed"}, {**self.receipt("test"), "roots": []}):
            with self.assertRaises(ValueError):
                check_receipt(receipt, "prod", IDENTITY)

    def test_new_commit_digest_run_or_retry_cannot_reuse_success(self):
        for key in IDENTITY:
            with self.subTest(key=key), self.assertRaises(ValueError):
                check_receipt({**self.receipt("test"), key: "changed"}, "prod", IDENTITY)

    def test_plan_integrity_and_expiry(self):
        now = datetime.now(timezone.utc)
        plan = {**IDENTITY, "environment": "prod", "root": "prod", "created_at": now.isoformat(),
                "config_sha256": "config", "lock_sha256": "lock"}
        check_plan(plan, IDENTITY, "prod", "prod", now, "config", "lock")
        for key, value in (("created_at", (now - timedelta(hours=7)).isoformat()),
                           ("created_at", (now + timedelta(seconds=1)).isoformat()),
                           ("root", "dev"), ("config_sha256", "changed"), ("lock_sha256", "changed"), ("sha", "new")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                check_plan({**plan, key: value}, IDENTITY, "prod", "prod", now, "config", "lock")


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.environment = {"deployment_branch_policy": {"custom_branch_policies": True, "protected_branches": False},
            "protection_rules": [{"type": "required_reviewers", "prevent_self_review": True,
                                                            "reviewers": [{"type": "Team", "reviewer": {"id": 1}}]}]}
        self.branches = {"branch_policies": [{"name": "main", "type": "branch"}]}

    def test_protected_environment(self):
        check_environment(self.environment, self.branches, True)

    def test_missing_manual_approval_is_rejected(self):
        self.environment["protection_rules"] = []
        with self.assertRaises(ValueError):
            check_environment(self.environment, self.branches, True)

    def test_self_review_is_rejected(self):
        self.environment["protection_rules"][0]["prevent_self_review"] = False
        with self.assertRaises(ValueError):
            check_environment(self.environment, self.branches, True)

    def test_wildcards_tags_and_extra_branches_are_rejected(self):
        for rules in ([{"name": "*", "type": "branch"}], [{"name": "main", "type": "tag"}],
                      self.branches["branch_policies"] + [{"name": "develop", "type": "branch"}]):
            with self.assertRaises(ValueError):
                check_environment(self.environment, {"branch_policies": rules}, True)
