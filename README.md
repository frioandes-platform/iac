# frioandes-platform/iac

Terraform for the FríoAndes cloud platform, on Azure with the `azurerm`
provider. This repository holds the infrastructure as code; the architecture
decisions, the verified address plan and the firewall policy table live in
[`frioandes-platform/planning`](https://github.com/frioandes-platform/planning).

## Layout

```
modules/        reusable Terraform modules
  network/       virtual network and 11 subnets of one environment (issue #20)
    data/          pinned source files and strict CSV for Terraform
environments/   one folder per environment, each calling the modules above
  dev/
  test/
  prod/
scripts/        data verification and local Terraform checks
tests/          Python verifier regression tests
VALIDATION.md   recorded validation results and their scope
```

A module is written once and instantiated per environment by changing only
its input variables, so the same network pattern does not get rebuilt by
hand for every environment.

## Conventions

- Code and comments in English. Decisions and their reasoning live in the
  planning repo, in Spanish.
- A module never hardcodes a value that is already verified in the planning
  repo (an address range, a firewall rule). It reads the data file instead,
  and the module's README says which file and what its hash was when copied.
- `environments/<env>` is the only place that calls `terraform plan` or
  `terraform apply`. Modules are not applied directly.

## Validate without an Azure subscription

Requirements: Terraform >= 1.7 and < 2, Python >= 3.10, and internet access
for provider initialization. Each environment root pins AzureRM to 4.62.0.

From the repository root:

```bash
terraform fmt -recursive
bash scripts/check.sh
```

The script verifies snapshot hashes and address safety, runs the Python
regression tests, checks formatting, initializes each environment with
`-backend=false`, validates the configuration and executes mocked Terraform
plans for dev, test and prod. These checks do not require Azure authentication
and do not create cloud resources.

Commit the generated `environments/<env>/.terraform.lock.hcl` files. Keep
`.terraform/`, local tfvars, plans and state files out of version control.
The completed checks and the limits of their evidence are documented in
[VALIDATION.md](VALIDATION.md).

## Address-plan compatibility and module scope

The module selects all 11 subnets for an application environment from the
reviewed plan. It does not create the hub, on-premises sites, VPNs, peering,
firewall, NSGs, route tables, DNS Resolver or application services. Subnet IDs
are exposed for subsequent security and workload modules. Network security
and routing must be integrated before workloads use the network.

Terraform reads the corrected `ip-plan.csv` directly from planning commit
`bcb98b538ac7df7f8733c7ed949cef9290d650bc`. The canonical
`ip-plan.terraform.csv` remains an additional reproducibility check.
All network names, CIDRs and service selections remain unchanged.

When updating an approved snapshot, review its provenance, regenerate the
strict CSV and rerun the complete validation before committing it:

```bash
python3 scripts/prepare_network_data.py
terraform fmt -recursive
bash scripts/check.sh
```

## Running an environment when an Azure subscription is available

Configure the approved Azure identity and `ARM_SUBSCRIPTION_ID` for the
selected environment before running an authenticated plan. Platform bootstrap
must register the required Azure resource providers; automatic registration
is disabled in these roots. Each root owns a resource group; import an
existing group first rather than managing it from multiple states.


```bash
cd environments/dev
terraform init
terraform plan -out=plan.tfplan
```

`terraform apply` is not part of this issue's scope: there is no Azure
subscription wired up yet, and the CI/CD pipeline that will run `plan` and
`apply` with OIDC and an approval gate is issue #23.

Remote state with a separate key per environment is to be configured with
#23 before shared deployment. The current backend-free checks do not establish
that backend or an OIDC pipeline. Given a real plan, its network names and
CIDRs can also be checked against the selected environment's snapshot:

```bash
terraform show -json plan.tfplan > plan.json
python3 ../../scripts/verify_network.py --environment dev --plan-json plan.json
```

Run these commands from `environments/dev`; use the matching root and
`--environment` value for test or prod.

## Modules

- [`modules/network`](modules/network/README.md): virtual network and
  subnets for one environment, from `frioandes-platform/planning` issue #8.

## Related planning issues

- [#8](https://github.com/frioandes-platform/planning/issues/8) network topology and the verified IP plan this module reads.
- [#20](https://github.com/frioandes-platform/planning/issues/20) this repository and the network module.
- [#21](https://github.com/frioandes-platform/planning/issues/21) the security module, checked against the firewall policy table.
- [#23](https://github.com/frioandes-platform/planning/issues/23) the CI/CD pipeline that will plan and apply these environments.
