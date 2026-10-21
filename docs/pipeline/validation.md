# Pipeline validation record (#23)

## Baseline and unchanged contracts

Prepared against `frioandes-platform/iac` main commit
`bbd5fd3fdf906ae5ab92224b9d266b9e673288aa`, which includes the reviewed #20
and #21 implementations. #22 remains a separate PR at preparation time; the
pipeline selects `check-ingest.sh` automatically when it is present.

The network/security module code, source CSVs, provenance files and all four
AzureRM 4.62.0 lock files are unchanged. New partial backend blocks configure
remote state at the environment roots without changing network IDs or rules.
No bytecode, provider cache, local state, secrets or generated plans are delivered.

## Checks executed in the authoring workspace

| Check | Result |
| --- | --- |
| Pipeline policy, workflow and driver tests | 38 passed |
| Existing network/security Python regression tests | 17 passed |
| Approved snapshot hashes and non-overlap | Passed: 3 application VNets, 33 subnets, 23 on-premises subnets |
| GitHub workflow lint | Passed with actionlint 1.7.7, including custom runner labels |
| Terraform formatting | Passed with Terraform 1.9.8 |
| Shell syntax and whitespace | Passed |
| Demonstration Go binary | Compiled with Go 1.27.3; `--self-test` passed |
| Provider initialization | Dev `init -backend=false -lockfile=readonly` succeeded with the verified local AzureRM mirror |

The new tests cover the 04:00/22:00 Bogotá boundaries, midnight, a 30-minute
remaining-window budget, campaign overlap and unknown/expired controls, incident
authorization bound to the release, missing approval, self-review or broad branch policies,
ordered promotion, stale/altered plans, immutable action references, and the real
driver's gate-before-each-apply ordering with fake CLI/cloud responses. A freeze
between shared and prod roots blocks the second apply and emits no success receipt.
They also protect the promotion outputs from accidental masking of public release
identifiers and ensure ACR authentication uses the registry's own subscription.

These driver fixtures are synthetic; they are not authenticated Terraform plans.

## Limitations and pending evidence

- Docker is unavailable in the authoring workspace. The actual Docker build,
  container execution and ACR push have not been executed here. Compiling the
  Go binary and running its self-test is a narrower check.
- AzureRM provider-schema validation could not run in this workspace: after
  installation the provider failed the plugin startup handshake. This environment
  has the previously observed Unix-socket restriction. No new successful full
  run of `check-security.sh` or `check-ingest.sh` is claimed for this revision.
- The user's earlier successful #20/#21/#22 module runs are prior evidence,
  not a new run of this pipeline revision.
- No GitHub workflow run, real Environment approval, Azure OIDC login, Key Vault
  read, authenticated Terraform plan/apply, live campaign denial or incident
  deployment has been performed for #23.
- The public GitHub REST Environment schema was checked. Administrator bypass
  is not an exposed response field; its disabled UI setting requires separate
  bootstrap confirmation and is not falsely reported as an automated check.
- The operational campaign calendar, seven identities, bootstrap infrastructure
  and protected environments still need real client/administrator configuration.

Cloud promotion remains explicitly disabled. This record establishes local
code-level evidence, not an operational production deployment certification.

## Contributor and GitHub confirmation

Run from the repository root, using a Python environment with PyYAML 6.0.3:

```bash
bash scripts/check-pipeline.sh
terraform fmt -check -recursive
bash scripts/check-security.sh
# If #22 has been merged: bash scripts/check-ingest.sh
```

With Go 1.27.3 and Docker, also run:

```bash
python3 scripts/pipeline/run.py build-local
```

The PR workflow runs the linter, mocked module checks and Docker image test on
GitHub-hosted Ubuntu without Azure credentials. Record its run URL and outcome
once it actually completes. After the bootstrap, use the live validation matrix
in [bootstrap.md](bootstrap.md) and append the resulting evidence here.
