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

On every merge to `main`, and on a manual run, the `baseline` job prices the
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

### Setup

1. Get a free API key: install the Infracost CLI and run `infracost auth login`.
2. Add it as the repository secret `INFRACOST_API_KEY`
   (**Settings → Secrets and variables → Actions**).

Without the secret, the jobs print a notice and skip the estimate. Pull requests
from forks never receive the secret, so they also skip it. The workflow uses
`pull_request`, never `pull_request_target`, so code from a pull request never
runs with write access or with the secret of another branch.
