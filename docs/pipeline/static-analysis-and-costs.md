# Static analysis and cost estimates

Three checks run on every pull request without an Azure login. TFLint and
Checkov block the merge when they fail. Infracost reports the cost of the change
and never blocks.

| Tool | Where | What it checks | Blocks the merge |
| --- | --- | --- | --- |
| `terraform fmt` | `validate` job | Formatting | Yes |
| TFLint 0.64.0 with the AzureRM ruleset 0.32.0 | `static-analysis` job of `validate.yml` | Terraform errors and conventions (typed and unused variables, deprecated syntax) and AzureRM values the provider would reject | Yes |
| Checkov 3.3.26 | `static-analysis` job of `validate.yml` | Azure security misconfigurations: encryption, public access, NSGs, firewall settings | Yes |
| Infracost 0.10.46 | `costs.yml` | Monthly cost of the change, and of the whole infrastructure | No |

Run TFLint and Checkov locally with `bash scripts/check-static.sh`. TFLint needs
`GITHUB_TOKEN` to download the ruleset.

## Accepted Checkov findings

Each accepted finding is skipped **inline on its resource**, with the reason. No
check is disabled globally, so a new resource with the same problem still fails.

| Check | Resource | Why it is accepted |
| --- | --- | --- |
| `CKV2_AZURE_31` Subnet without NSG | `azurerm_subnet.firewall` (connectivity) | Azure does not allow an NSG on `AzureFirewallSubnet` or `AzureFirewallManagementSubnet` |
| `CKV2_AZURE_31` Subnet without NSG | `azurerm_subnet.this` (network module) | The NSGs are attached by `modules/security/subnet-controls`, a separate module Checkov cannot link to the subnet |
| `CKV_AZURE_216` Threat intelligence not in Deny | `azurerm_firewall.this` | Deny is set on the attached firewall policy, which governs a policy-managed firewall |
| `CKV_AZURE_220` IDPS not in Deny | `azurerm_firewall_policy.this` | IDPS needs the Premium tier. The design keeps Standard (`firewall-settings.csv`, `sku_tier`) and moves to Premium only if encrypted traffic must be inspected |

A new skip needs the same treatment: an inline comment with the reason, and a row
in this table, reviewed in the pull request.

## Cost of each change (Infracost)

When a pull request touches `environments/`, `modules/` or the Infracost files,
`costs.yml` prices the base branch and the pull request from the Terraform code
and posts **one comment** with the monthly difference and the new monthly cost
of every root (connectivity, dev, test, prod), also when a root does not change. Each new push updates that comment. The run summary has the same
table.

On matching changes to `main`, and on a manual run, the `baseline` job prices the
whole infrastructure and writes the monthly cost per root and per resource in the
run summary.

How the figures are obtained:

- Infracost reads the HCL; it needs no Terraform plan and no Azure credentials.
  The code goes to the Infracost pricing API only as resource types and
  attributes, not as values from Key Vault.
- Prices are Azure list prices in USD for the region in the code.
- Usage-based prices (firewall data processed) come from `infracost-usage.yml`,
  which follows the cost document in `frioandes-platform/planning`. Update it when
  those figures change.
- The estimate covers what is in this repository. The full project cost,
  including Fabric, licences, migration and campaign, is in the planning cost
  document, not here.

### Explicit ingestion estimate and capacity comparison

`infracost.yml` now selects public, synthetic inputs from `costs/inputs/`.
Its canonical estimate includes dev ingestion at **one Standard throughput
unit (TU)** and the shared Event Hubs DNS zone. These inputs are exclusively
for estimating, not a working Azure subscription or a deployment configuration.
They are outside the Terraform roots and are never auto-loaded: dev still has
`ingest = null`, and connectivity DNS remains disabled by default.

The ingest module accepts `capacity`, defaulting to 1. Dev forwards the
optional `ingest.capacity`, also defaulting to 1, so existing callers remain
compatible. SKU stays Standard, auto-inflate stays off, and the module validates
whole numbers from 1 to 40. AzureRM 4.62.0 uses an integer field; the Standard
upper bound follows [Azure's Event Hubs quotas](https://learn.microsoft.com/en-us/azure/event-hubs/event-hubs-quotas).
See the [pinned provider schema](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.62.0/internal/services/eventhub/eventhub_namespace_resource.go).
This does not configure Premium processing units or assert subscription quota.

All scenarios use the real `environments/` roots and their local modules:

| Scenario | dev | connectivity | test / prod |
| --- | --- | --- | --- |
| `disabled` | Ingestion off | Event Hubs DNS off | Existing network/security |
| `1tu` | Ingestion on, capacity 1 | One shared zone, links to hub and dev | Same |
| `2tu` | Ingestion on, capacity 2 | Identical to `1tu` | Same |

Every scenario contains exactly connectivity, dev, test and prod, once each.
There is one shared firewall, owned by connectivity. Dev references that root's
DNS zone using a synthetic resource ID; it does not create another zone or
firewall. The synthetic VNet ID matches the approved dev VNet's name, without
copying or changing any CIDR. RBAC uses sample Entra object UUIDs, and the
security-token values match the existing public test fixture. They are not
approved production identities, addresses or DNS records.

The estimate retains East US 2, Standard, two Event Hub partitions, seven days
of retention, a private endpoint, public access and SAS disabled, Entra roles
and the existing network/security module references. It does not deploy sensors,
Stream Analytics, a notifier application or any other unimplemented service.

Usage assumptions are shared by all scenarios:

- Firewall: the existing 18,293 GB/month planning assumption is unchanged.
- Event Hubs: **1,000,000 ingress events/month**, a synthetic demonstration
  assumption, not observed telemetry or a measured forecast.
- `throughput_or_capacity_units` is deliberately absent from the usage file.
  Infracost 0.10.46 can use that field to override Terraform capacity; setting
  it would hide the input change. Capacity comes from Terraform instead. See
  the [pinned Event Hubs pricing adapter](https://github.com/infracost/infracost/blob/v0.10.46/internal/providers/terraform/azure/event_hubs_namespace.go).
- Private endpoint traffic and DNS query volumes have not been estimated.
  Their usage-dependent costs can remain unknown; the result is not a complete
  operating budget. Prices depend on the live pricing catalog and query date.

`scripts/infracost_scenarios.py` clones the canonical configuration, generates
explicit temporary tfvars, and prices three breakdowns plus two comparisons.
The `1tu` and `2tu` configurations differ only in the Terraform input
`ingest.capacity`; region, traffic, DNS, endpoint, security and other roots stay
the same. Generated configurations, results and provenance belong in a temporary
directory, not in the deployment roots or version control.

### Commands for the live demonstration

Use Infracost 0.10.46 and Python with PyYAML 6.0.3. Use already configured
Infracost authentication; do not paste keys into commands, chat or logs.
No Azure login, Terraform plan or subscription is required for these commands.

To inspect all three input sets **without querying any price**:

```bash
cost_output_dir=$(mktemp -d /tmp/frioandes-costs.XXXXXX)
python3 scripts/infracost_scenarios.py --prepare-only --output-dir "$cost_output_dir"
```

To price the canonical four-project estimate, including dev ingestion:

```bash
infracost breakdown --config-file=infracost.yml --format=table --show-skipped
```

To calculate and compare the three controlled scenarios:

```bash
python3 scripts/infracost_scenarios.py --output-dir "$cost_output_dir"
infracost output --path="$cost_output_dir/1tu.json" --format=table --show-skipped
infracost output --path="$cost_output_dir/capacity-diff.json" --format=diff --show-skipped
cat "$cost_output_dir/provenance.json"
```

The directory contains `disabled.json`, `1tu.json`, `2tu.json`,
`enablement-diff.json`, `capacity-diff.json`, `summary.md`, the exact generated
configurations/tfvars and `provenance.json`. `--prepare-only` generates no price
results. A failed pricing run leaves provenance marked incomplete and must not
be presented as successful pricing.

The existing `costs.yml` now also runs the `scenarios` job on matching pull
requests, main pushes and manual dispatch. It uses the existing repository
secret, a GitHub-hosted runner and read-only repository permissions, without
Azure OIDC. Its run summary shows the two estimates, both differences and
provenance. Missing credentials cause an explicit notice and skip, not a
successful price query. The existing base→PR comparison and updating PR comment
are retained; changes under `costs/` or to the runner script trigger the workflow.

For a live PR demonstration **after this scenario setup is in the base branch**,
change only `ingest.capacity` from 1 to 2 in `costs/inputs/dev.tfvars.json`.
The PR comment then compares the same ingestion/DNS configuration and exposes
the capacity increment. Tests permit this valid input change. Before that
setup is in the base branch, this PR's base→PR difference includes **enabling
ingestion and DNS**, so it must not be labelled a capacity-only increase. Use
the `scenarios` job's controlled `capacity-diff` for that demonstration now.

### Interpreting and identifying the evidence

- `enablement-diff`: disabled→1 TU includes the namespace, private endpoint,
  shared DNS and any separately billable usage. It is the component-enablement
  increment, not the price of adding a second TU.
- `capacity-diff`: 1→2 TUs isolates the Terraform capacity input. Inspect the
  Event Hubs namespace's capacity component; a zero/missing delta needs
  investigation, not a claim that capacity is free.
- Resources shown by `--show-skipped`, unsupported resources, missing prices
  and costs with unknown usage are distinct from a verified zero price.
  Resource groups, networks, NSGs, RBAC and consumer groups may be unpriced or
  have no separate charge. Inspect the output classification; do not infer
  either condition solely from an empty cost column.
- These are monthly Azure list-price estimates in USD, not a subscription
  bill, a live performance test or a guarantee of regional availability.

Record the run URL, attempt, checkout commit, PR head/base and inputs SHA-256
from the scenario job summary. GitHub may check out a synthetic PR merge commit;
the separately recorded head SHA identifies the contributor's source commit.
`provenance.json` also records UTC time, CLI version, per-file hashes and whether
the working tree was dirty. A local dirty checkout cannot be identified by its
commit alone. To reproduce the input set, check out the recorded commit and
use the same CLI, tfvars and usage assumptions; a later catalog query can have
different prices. The current local work has no new Actions run or committed
revision yet.

### Verification of this revision — 2026-10-28

Branch: `ci/infracost-verification`; base: updated main
`01d9942b7237a58e5fe3fc4d317188016f47b9d2`. The initial working tree was clean.
The diagnostic PR #7 is not a dependency; its changes are not included.

Local tools: Python 3.12.3, PyYAML 6.0.3, Terraform 1.16.6, AzureRM 4.62.0,
TFLint 0.64.0 with AzureRM ruleset 0.32.0, Checkov 3.3.26,
actionlint 1.7.7 and Infracost 0.10.46. TFLint and Infracost downloads were
verified against their official release checksums and installed in `/tmp`;
Checkov used a temporary virtual environment. Terraform differs from the
workflow's pinned 1.9.8; no local execution with 1.9.8 is claimed.

The commands used the existing `.venv` for PyYAML and the temporary tool
directories below; no scanner integration or version pin was changed:

```bash
git diff --check
PATH="$PWD/.venv/bin:/tmp/frioandes-pipeline-repair/actionlint-bin:$PATH" bash scripts/check-pipeline.sh
terraform fmt -check -recursive
bash scripts/check-ingest.sh
PATH="/tmp/frioandes-infracost-verification/bin:/tmp/frioandes-infracost-verification/checkov/bin:$PATH" bash scripts/check-static.sh
python3 scripts/pipeline/run.py build-local
.venv/bin/python scripts/infracost_scenarios.py --prepare-only --output-dir /tmp/frioandes-infracost-verification/final
```

| Verification | Observed local result |
| --- | --- |
| Whitespace and Terraform formatting | Passed |
| Pipeline, scenario and workflow tests | 57 passed; actionlint passed |
| Existing network/security Python tests and approved snapshot checks | 17 passed; hashes and non-overlap passed |
| Terraform ingestion/security checks | Backend-disabled init and validate passed; mocked tests passed: connectivity 4, dev 16, test 2, prod 3 (25 total, zero failures); all seven firewall/NSG comparisons passed |
| Capacity coverage | Omitted capacity defaults to 1; 2 and 40 accepted; 0, -1, 1.5 and 41 rejected; dev forwards the configured estimation capacity |
| Controlled scenario coverage | Four roots per scenario; 1→2 changes only capacity; enablement includes shared DNS; usage cannot override capacity; valid live input edit and provenance covered |
| TFLint / Checkov | Passed; Checkov: 15 passed, 0 failed, 4 existing inline skips |
| Demonstration image | Local build and non-root self-test passed with Go 1.22.2 and Docker 29.8.2 |
| Scenario preparation | Three real configurations/tfvars and provenance generated; no prices queried |

Local pricing was attempted with the real canonical configuration and exited 1:
`INFRACOST_API_KEY is not set but is required`. No local dollar amounts, price
queries, capacity cost delta or successful remote run are claimed. Actions must
still execute all three breakdowns, both comparisons and the scenario summary
with the configured repository secret at the final PR commit.

### Setup

1. Get a free API key: install the Infracost CLI and run `infracost auth login`.
2. Add it as the repository secret `INFRACOST_API_KEY`
   (**Settings → Secrets and variables → Actions**).

Without the secret, the jobs print a notice and skip the estimate. Pull requests
from forks never receive the secret, so they also skip it. The workflow uses
`pull_request`, never `pull_request_target`, so code from a pull request never
runs with write access or with the secret of another branch.
