# Ingest validation record — planning #22

## Scope and baseline

Prepared on 2026-10-21 against IaC security commit
`ba083b0e5d802527b13b09e679ab8f4c5037952d`, including the corrected network
commit `80bce9aecfe653a6c81b8eda41d1473421325373`.

The delivery adds the representative alert Event Hub from planning #13 to
`modules/ingest`, an optional reference call in dev, and shared DNS support in
connectivity. It does not change #20/#21 module code, source CSVs, hashes or locks.

## Executed in the authoring environment

| Check | Result | Limit |
|---|---|---|
| `python3 scripts/verify_network.py` | PASS | Source snapshots, containment and non-overlap; not a deployment |
| Python regression suite | 17 passed | Existing network/security verifier tests; not Event Hubs runtime tests |
| `terraform fmt -check -recursive` | PASS, Terraform 1.9.8 | HCL formatting/syntax, not provider-schema validation |
| Shell syntax and smoke-test CLI help | PASS | Does not contact Event Hubs |
| Exact module variables and preconditions through Terraform Core | 6 cases passed | Original variable declarations and lifecycle expressions evaluated with the built-in `terraform_data` resource; AzureRM resources/schema were not evaluated |
| Dev `terraform init -backend=false -input=false -lockfile=readonly` | PASS | AzureRM 4.62.0 from the existing local mirror; checked against the unchanged provider lock |
| Dev `terraform validate` | BLOCKED | Provider could not start its local plugin connection; socket creation is denied in this execution environment |
| New AzureRM-backed mocked tests | NOT EXECUTED | Require the provider schema; must run on the reviewer's supported machine |
| Authenticated Azure plan/apply and live send/receive | NOT EXECUTED | No deployment subscription or approved live inputs supplied |

The six Core cases accept the dev contract and the production rule ID mapping;
reject `snet-ingest`, disabled private-endpoint NSG enforcement, a missing notifier
rule, and an invalid private DNS zone ID. These are a limited contract check,
not a substitute for the provider-backed test suite.

## Required local check before review completion

From the IaC repository root:

```bash
terraform fmt -recursive
bash scripts/check-ingest.sh
```

This runs the existing #20/#21 checks, including all seven policy comparisons,
and the seven added Terraform test runs:

- Workload remains absent when the dev opt-in input is null.
- Mock apply checks actual network/security module wiring, private DNS reference,
  general public access/SAS disabled, TLS, capacity/retention and entity-scoped roles.
- Approved isolated module contract and the trusted-services exception.
- Rejection of the sensor-ingestion subnet.
- Rejection of disabled private-endpoint NSG enforcement.
- Rejection of a missing notifier allow rule.
- Shared DNS ownership and hub/dev links.

Every new test file declares `mock_provider "azurerm"`. No real apply is issued by
the shell script. Record the actual result and versions here after execution;
do not replace the pending status with a claim based on the earlier #21 run.

After code is committed, #21's existing report remains evidence for its original
SHA. If a new security report is needed for the combined #22 commit, rerun the
security checks on that commit and regenerate the report; do not merely edit its
referenced SHA.

## Acceptance mapping

| #22 criterion | Implementation | Evidence still needed |
|---|---|---|
| References existing network and security modules | Dev passes subnet ID, endpoint policy mode, NSG ID and rule IDs from module outputs, with an explicit dependency on completed subnet controls | Successful AzureRM-backed integration test on the delivered revision |
| Traceable to Carga A or Carga B | README cites planning #13 sections 3.2 and 5.2 and its exact source revision; the resource is the alert Event Hub | Architecture review of this selected representative scope |

The code addresses the two deliverable criteria. The story's phrase "running"
and its end-to-end demonstration additionally require a real deployment and live
test. Neither is claimed complete. The module README includes DNS, positive and
negative network/identity checks and the optional synthetic smoke-test command.
