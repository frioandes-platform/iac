# network module

Creates the virtual network and subnets of one FríoAndes application environment
(`prod`, `test` or `dev`). The address plan is read from `data/ip-plan.csv`, not
hardcoded, so the same module code works for every environment.

## Source of truth

`data/ip-plan.csv` is a copy of `docs/architecture/red/data/ip-plan.csv` from
`frioandes-platform/planning` (issue #8), verified there with
`tools/verify_ip_plan.py` (12 checks, no overlap with the 23 on-premises
subnets of Cali and the 8 regional centers).

sha256 of the planning repo's file, as verified there: `2af88d980e4de7b6c83f0e5bf0f123c544d235a80017dc8e42fc109b5608be42`
sha256 of the copy in this module: `ef6f3b544c9187d8e21127e0354b51b4c27c6ae911b059d215be1b5f9326acb3`

The two hashes differ on purpose. Six rows (the `snet-data-pe` and
`snet-archive` rows for prod, test and dev) have a `notes` field with commas
that are not wrapped in quotes. Python's CSV reader tolerates that and
returns extra fields; Terraform's `csvdecode`, backed by Go's strict CSV
parser, rejects the row outright. This copy re-quotes those six `notes`
fields, rejoining the split tokens; every other column in every row is
unchanged. This should be fixed at the source in the planning repo, so this
re-quoting step is not needed here on the next copy.

If the source file changes in the planning repo, copy it here again, re-quote
any row Terraform rejects the same way, update both hashes above, and re-run
the verification described below.

## What it creates

For the given `environment`, one virtual network and every subnet listed for
that environment in `data/ip-plan.csv`. The `hub` and `reserva` rows are
excluded: the hub is a separate, shared network module, not part of an
application environment.

| Subnet | Service | Delegation |
|---|---|---|
| `snet-ingress` | app-gateway-v2 | none |
| `snet-app-torre` | container-apps-workload-profiles | `Microsoft.App/environments` |
| `snet-app-portal` | container-apps-workload-profiles | `Microsoft.App/environments` |
| `snet-data` | mysql-flexible | `Microsoft.DBforMySQL/flexibleServers` |
| `snet-data-pe` | private-endpoints | none, private endpoint network policies disabled |
| `snet-archive` | private-endpoints | none, private endpoint network policies disabled |
| `snet-ingest` | private-endpoints | none, private endpoint network policies disabled |
| `snet-admin` | admin-agents | none |
| `snet-cali-integration` | migration-tools | none |
| `snet-fabric-egress` | fabric-vnet-gateway | `Microsoft.PowerPlatform/vnetaccesslinks` |
| `snet-telemetry-func` | functions-flex | `Microsoft.App/environments` |

Delegation requirements come from
`docs/architecture/red/data/azure-subnet-constraints.csv` in the planning repo.

## Inputs

| Name | Description | Default |
|---|---|---|
| `environment` | `prod`, `test` or `dev` | required |
| `resource_group_name` | resource group for the vnet and subnets | required |
| `location` | Azure region | `eastus2` |
| `tags` | tags applied to every resource | `{}` |

## Outputs

`vnet_id`, `vnet_name`, `subnet_ids` (map by subnet name), `subnet_cidrs` (map
by subnet name, taken from the CSV).

## Reusing the same module across environments

`environments/dev`, `environments/test` and `environments/prod` call this
module with the same code and only change `environment` and
`resource_group_name`. See the top-level README for how to run each one.

## Verifying a plan against the IP plan

From a clone of `frioandes-platform/planning`, inside `docs/architecture/red/`:

```bash
terraform -chdir=../../../iac/environments/dev plan -out=plan.tfplan
terraform -chdir=../../../iac/environments/dev show -json plan.tfplan > plan.json
python3 tools/compare_tfplan.py --tfplan plan.json --plan data/ip-plan.csv --out-csv tf-ip-plan.csv
python3 tools/verify_ip_plan.py --plan tf-ip-plan.csv --out verification/reporte-terraform.md
```

This is the check the network design (`docs/architecture/red-topologia-subnetting.md`,
section 4.8) expects before trusting what Terraform actually deploys.

Note: `compare_tfplan.py` compares against the full `ip-plan.csv`, which also
has hub, test and prod rows. Run it against a single environment's plan and
it will correctly report the other environments as missing, because they are
not part of that plan. The comparison only reaches exit code 0 once every
environment (and the hub module, outside the scope of this one) has been
planned together, or once the script is pointed at a CSV filtered to the
environment under test.
