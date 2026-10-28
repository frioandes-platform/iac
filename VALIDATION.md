# Validation record

## Review corrections

This revision addresses the review of
[iac PR #2](https://github.com/frioandes-platform/iac/pull/2), tracked in
[planning issue #20](https://github.com/frioandes-platform/planning/issues/20).

- Removed all three tracked Python bytecode files and ignored `__pycache__/`
  and `*.pyc`.
- Stopped ignoring `.terraform.lock.hcl` and included the lock files for dev,
  test and prod, with AzureRM 4.62.0 and official package checksums.
- Added this file to resolve the README's missing validation-record link.
- Updated the exact planning snapshot and `source.json` to commit
  `bcb98b538ac7df7f8733c7ed949cef9290d650bc` (planning PR #64).
- Terraform now reads the corrected `ip-plan.csv` directly. The canonical
  `ip-plan.terraform.csv` remains an additional reproducibility check; the
  generator rejects malformed rows and preserves all ten fields.

The source IP-plan SHA-256 is
`a520eba842e6d7781705613d539fcfd018bfd00481f3842814d07d97036b91a0`.
The on-premises inventory is unchanged. The first nine fields of all 44
address-plan rows match the previous snapshot, so the network names, CIDRs,
service selections and delegations remain unchanged.

## Checks executed on this revision

- Snapshot SHA-256 and Git blob hashes match the pinned sources.
- Three application VNets and 33 application subnets pass containment and
  non-overlap checks against each other, the hub, reservations and all 23
  on-premises subnets.
- Seven Python unittest cases passed, including checksum tampering, malformed
  CSV, overlaps and incomplete or incorrect synthetic Terraform-plan fixtures.
- `terraform fmt -check -recursive` passed with Terraform 1.9.8.
- Terraform Core's `csvdecode` read the corrected source directly and returned
  all 44 rows in a provider-free console evaluation.
- `bash -n scripts/check.sh` and `git diff --check` passed.
- Initialization with `-backend=false` succeeded for all three environment
  roots, using a local mirror of the official AzureRM 4.62.0 ZIP after verifying
  its SHA-256 against HashiCorp's published checksum. The mirror configuration
  and downloaded binaries are outside the repository and are not delivered.

Direct registry discovery timed out in the authoring environment. After the
provider was installed, `terraform validate` could not load its schema:
the provider debug log reported `listen unix ...: socket: operation not permitted`.
This is a restriction of the execution environment. Therefore this revision
does **not** claim successful provider-schema validation or mocked Terraform
tests, nor a successful end-to-end run of `scripts/check.sh`.

The earlier version's full check run passed on the contributor's Ubuntu and
was independently confirmed in the issue review. Those earlier results are
not presented as a new full run of this corrected revision.

## Required confirmation on the contributor's machine

From the repository root, run:

```bash
terraform fmt -check -recursive
bash scripts/check.sh
```

The complete run must pass verification, all seven Python tests, formatting,
and `init`, `validate` and mocked `test` for dev, test and prod. Record the
result in the PR and update this record after it succeeds. Keep the three
provider lock files tracked; keep caches, local inputs, plans and state out
of version control.

No authenticated Azure plan or apply was run. Mocked plans and synthetic
verifier fixtures do not establish live connectivity or a successful cloud
deployment. Deployment remains subject to the future subscription,
credentials and approved process.

## Successful verification on the contributor's Ubuntu machine

After the review corrections, `bash scripts/check.sh` completed successfully:

- Snapshot hashes and non-overlap verification passed.
- All seven Python tests passed.
- Terraform formatting checks passed.
- AzureRM 4.62.0 initialized successfully in dev, test and prod.
- Terraform validation passed in all three environments.
- Mocked Terraform tests passed: three passed, zero failed.

This successful local run completes the provider validation previously
pending in the authoring environment. No authenticated Azure plan or
apply was executed.

## Validation on the developer workstation

`bash scripts/check-ingest.sh` completed successfully with AzureRM 4.62.0.

- All 17 Python regression tests passed.
- Snapshot integrity and network non-overlap checks passed.
- Terraform formatting and configuration validation passed.
- Mocked Terraform tests passed in connectivity, dev, test and prod,
  including the ingestion integration and rejection scenarios.
- All seven security comparisons completed without discrepancies.
- Verification evidence hashes were recorded.

This execution resolves the provider-validation limitation recorded during
authoring. No authenticated Azure deployment or live send/receive test was run.

## Successful verification on the contributor's Ubuntu machine

The following checks completed successfully on this revision:

- Pipeline policy, workflow and driver tests: 47 passed.
- Existing network/security Python tests: 17 passed.
- Snapshot hashes and network non-overlap verification passed.
- Terraform formatting checks passed.
- AzureRM 4.62.0 initialization and Terraform validation passed
  for connectivity, dev, test and prod.
- Mocked Terraform tests passed in all four roots.
- All seven firewall/NSG comparisons concluded "sin discrepancias".

This completes the local Terraform validation previously blocked
in the authoring environment. Docker build, hosted GitHub Actions,
OIDC authentication and live Azure plan/apply remain unverified.
