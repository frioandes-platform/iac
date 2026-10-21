"""Pure release policy; no clock overrides or Azure access in the CLI."""
from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")
ROOTS = {"dev": ["dev"], "test": ["test"], "prod": ["connectivity", "prod"]}
# Each apply has a 20-minute process deadline, plus ten minutes of margin.
CHANGE_BUDGET_MINUTES = 30
MAX_PLAN_AGE = timedelta(hours=6)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "Timestamp must include a timezone")
    return result.astimezone(timezone.utc)


def window_gate(control, now, incident, repository, sha, run_id, run_attempt):
    """Allow only current, explicitly published operational controls."""
    require(now.tzinfo is not None, "Current time must be timezone-aware")
    require(control.get("schema_version") == 1, "Unknown control schema")
    require(type(control.get("campaign_active")) is bool, "Campaign status is required")
    issued, expires = instant(control["issued_at"]), instant(control["valid_until"])
    end = now + timedelta(minutes=CHANGE_BUDGET_MINUTES)
    require(issued <= now < expires and end < expires, "Operational control is expired or too short-lived")
    require(expires - issued <= timedelta(hours=24), "Publish operational controls at least daily")
    windows = control.get("campaign_windows")
    require(isinstance(windows, list), "A confirmed campaign calendar is required")
    upcoming_campaign = False
    for window in windows:
        start, finish = instant(window["start"]), instant(window["end"])
        require(start < finish, "Invalid campaign interval")
        upcoming_campaign |= now < finish and end >= start
    if incident:
        require(re.fullmatch(r"INC-[A-Z0-9-]{3,60}", incident) is not None, "Invalid incident identifier")
        entries = [x for x in control.get("incidents", []) if x.get("id") == incident]
        require(len(entries) == 1, "Incident has not been independently authorized")
        entry = entries[0]
        expected = {"status": "declared", "repository": repository, "sha": sha,
                    "run_id": str(run_id), "run_attempt": str(run_attempt), "environment": "prod"}
        require(all(entry.get(k) == v for k, v in expected.items()), "Incident authorization does not match this release")
        require(isinstance(entry.get("approved_by"), str) and bool(entry["approved_by"].strip()), "Incident approver is required")
        require(re.fullmatch(r"https://github\.com/frioandes-platform/planning/issues/[1-9][0-9]*", entry.get("record_url", "")) is not None,
                "A planning incident record is required")
        require(instant(entry["valid_from"]) <= now and end < instant(entry["valid_until"]), "Incident authorization expired or too short-lived")
        return f"Incident exception {incident}; promotion and environment approval still required"
    require(control["campaign_active"] is False and not upcoming_campaign, "Production is frozen during or immediately before campaign")
    local = now.astimezone(BOGOTA)
    require(local.hour < 4 or local.hour >= 22, "Dispatch window 04:00-22:00 America/Bogota")
    cutoff = local.replace(hour=4, minute=0, second=0, microsecond=0)
    if local.hour >= 22:
        cutoff += timedelta(days=1)
    require(end < cutoff, "Insufficient time before dispatch; reserve 30 minutes")
    return "Production window and campaign gate passed"


def check_receipt(receipt, environment, identity):
    predecessor = {"dev": None, "test": "dev", "prod": "test"}[environment]
    if predecessor is None:
        require(receipt in ({}, None), "Development must start a new promotion chain")
        return
    require(isinstance(receipt, dict), "Previous environment receipt is required")
    require(receipt.get("environment") == predecessor and receipt.get("status") == "succeeded", "Previous environment did not succeed")
    require(all(receipt.get(k) == v for k, v in identity.items()), "Promotion must retain commit, image, run and attempt")
    require(receipt.get("roots") == ROOTS[predecessor], "Incomplete previous environment deployment")


def check_plan(manifest, identity, stage, root, now, config_sha, lock_sha):
    require(all(manifest.get(k) == v for k, v in identity.items()), "Saved plan belongs to another release")
    require(manifest.get("environment") == stage and manifest.get("root") == root, "Saved plan belongs to another environment")
    require(manifest.get("config_sha256") == config_sha and manifest.get("lock_sha256") == lock_sha, "Configuration or provider lock changed")
    age = now - instant(manifest["created_at"])
    require(timedelta(0) <= age <= MAX_PLAN_AGE, "Saved plan expired; restart the full promotion")


def check_environment(environment, branches, production=False):
    policy = environment.get("deployment_branch_policy") or {}
    require(policy.get("custom_branch_policies") is True and policy.get("protected_branches") is False,
            "Environment must use an explicit main-only branch policy")
    require([(x.get("name"), x.get("type")) for x in branches.get("branch_policies", [])] == [("main", "branch")],
            "Only the main branch may deploy; tags and wildcard policies are forbidden")
    if production:
        rules = [r for r in environment.get("protection_rules", []) if r.get("type") == "required_reviewers"]
        require(len(rules) == 1 and bool(rules[0].get("reviewers")), "Production needs required reviewers")
        require(rules[0].get("prevent_self_review") is True, "Production must prevent self-review")
        # The public Environment REST schema does not expose the admin-bypass
        # toggle. Disabling it is a required, separately reviewed UI bootstrap
        # setting; never invent an API field and reject every real response.
