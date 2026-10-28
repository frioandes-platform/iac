# frioandes-platform/iac

Terraform for the FríoAndes cloud platform, on Azure with the `azurerm`
provider. This repository holds the infrastructure as code; the architecture
decisions, the verified address plan and the firewall policy table live in
[`frioandes-platform/planning`](https://github.com/frioandes-platform/planning).

## Delivery pipeline (#23)

[Pipeline documentation](docs/pipeline/README.md) covers automatic plans,
OIDC/Key Vault, protected dev → test → prod promotion, private remote state,
container build/push and the dispatch/campaign gate. See the
[bootstrap runbook](docs/pipeline/bootstrap.md) before enabling cloud deployment
and the [validation record](docs/pipeline/validation.md) for executed checks.
Cloud promotion ships disabled until real Azure and GitHub prerequisites exist.

## tfsec security analysis

Install the checksum-pinned scanner with `python3 scripts/tfsec.py install`.
Run `python3 scripts/tfsec.py scan` and `python3 scripts/tfsec.py test-detection`.
The same commands run in the independent `tfsec` job on pull requests and pushes
to main. [Scope, limitations and demonstration](docs/pipeline/tfsec.md) explain
why zero findings must not be interpreted as complete coverage of CSV-driven rules.
`bash scripts/check-static.sh` also includes tfsec before TFLint and Checkov.

## Layout

```
modules/        reusable Terraform modules
  network/       virtual network and 11 subnets of one environment (issue #20)
    data/          pinned source files and canonical CSV verification copy
  security/      shared firewall policy and per-environment subnet controls (#21)
  ingest/        representative private telemetry alert buffer (#22)
environments/   one folder per environment, each calling the modules above
  dev/
  test/
  prod/
  connectivity/  shared hub firewall, policy and optional Event Hubs private DNS
scripts/        data verification and local Terraform checks
tests/          Python verifier regression tests
VALIDATION.md   network validation record from #20
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
tests for dev, test and prod, including a mock apply for ingest integration.
These checks do not require Azure authentication
and do not create cloud resources.

Commit the generated `environments/<env>/.terraform.lock.hcl` files. Keep
`.terraform/`, local tfvars, plans and state files out of version control.
The network checks and their limits are recorded in [VALIDATION.md](VALIDATION.md).
That record documents #20; it does not certify the later security changes.
The security cross-check belongs in `planning/docs/iac/verificacion-iac-vs-firewall.md`.

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
canonical verification copy and rerun the complete validation before committing it:

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
terraform init -backend-config=/approved/private/path/dev.backend.hcl
terraform plan -var-file=/approved/private/path/dev.tfvars.json -out=plan.tfplan
```

The original #20 module scope did not include an Azure apply. The #23 pipeline
now defines OIDC-backed plan/apply and production approval; cloud activation
still requires the bootstrap described above.

Each root now declares a partial Azure Blob backend for #23. An authenticated
local init requires the approved OIDC identity and backend configuration; plain
init is not sufficient until that configuration is supplied. Backend-free mocked
checks do not connect to remote state. Given a real plan, its network names and
CIDRs can also be checked against the selected environment's snapshot:

```bash
terraform show -json plan.tfplan > plan.json
python3 ../../scripts/verify_network.py --environment dev --plan-json plan.json
```

Run these commands from `environments/dev`; use the matching root and
`--environment` value for test or prod.

## Modules

- [`modules/ingest`](modules/ingest/README.md): private Event Hubs alert buffer from planning #13, implemented for #22.
- [`modules/security`](modules/security/README.md): shared firewall policy and application NSG controls from issue #21.
- [`modules/network`](modules/network/README.md): virtual network and
  subnets for one environment, from `frioandes-platform/planning` issue #8.

## Security implementation (#21)

`modules/security` creates the one shared hub firewall and its CSV-driven
policy. Its `subnet-controls` submodule attaches the application NSGs to the
network module outputs. `environments/connectivity` is the shared root; it
must use the connectivity subscription. Application roots retain their own
subscriptions and states.

Development is the initial reference environment. No production IPs or
provider domains are guessed: supply approved `security_token_values` before
an authenticated plan. Temporary access defaults to disabled and requires
individual selected IDs plus a migration change reference. Test fixtures are
fictitious and are not default deployment inputs.

This implementation is based on the corrected network commit
`80bce9aecfe653a6c81b8eda41d1473421325373`. The network and security copies of
`ip-plan.csv` are byte-identical; network inputs, outputs and subnet IDs retain
the #20 contract. The firewall policy CSV remains a separate approved source
for the traffic rules.

Run the complete security checks from the repository root:

```bash
terraform fmt -recursive
bash scripts/check-security.sh
```

This runs mocked provider tests and compares planned resources against the
pinned policy table, including the migration scenario. The ingest integration
also uses a mock apply; no resources are deployed in Azure.
See [modules/security/README.md](modules/security/README.md) for
scope, source hashes, control-point exclusions and the future routing/DNS
integration. The optional Terraform Core contract evaluation is explicitly
separate from provider-plan validation.

## Representative workload (#22)

`modules/ingest` creates the telemetry alert Event Hub from #13, sections 3.2
and 5.2. The optional dev root call references `module.network` and
`module.subnet_security`. General public access and SAS are disabled; the
private endpoint uses `snet-data-pe`. Entra roles are scoped to the alert hub.
The shared DNS zone remains owned by connectivity, linked to the hub and
explicit application VNets. Neither the network nor security CSV snapshot changes.

Run `bash scripts/check-ingest.sh` for #20/#21 regressions and the new tests.
See [the module README](modules/ingest/README.md) for opt-in inputs, cross-root
DNS activation, runtime checks and the exact scope of the representative component.
See [the validation record](docs/ingest-validation.md) for checks actually executed.
No IoT Hub, Stream Analytics job, notifier, live sensor or complete alert pipeline
is deployed by this module. A successful mocked test is not a live send/receive test.

## Related planning issues

- [#8](https://github.com/frioandes-platform/planning/issues/8) network topology and the verified IP plan this module reads.
- [#20](https://github.com/frioandes-platform/planning/issues/20) this repository and the network module.
- [#21](https://github.com/frioandes-platform/planning/issues/21) the security module, checked against the firewall policy table.
- [#22](https://github.com/frioandes-platform/planning/issues/22) the representative compute or ingestion module.
- [#23](https://github.com/frioandes-platform/planning/issues/23) the CI/CD pipeline that will plan and apply these environments.
