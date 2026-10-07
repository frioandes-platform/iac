# frioandes-platform/iac

Terraform for the FríoAndes cloud platform, on Azure with the `azurerm`
provider. This repository holds the infrastructure as code; the architecture
decisions, the verified address plan and the firewall policy table live in
[`frioandes-platform/planning`](https://github.com/frioandes-platform/planning).

## Layout

```
modules/        reusable Terraform modules
  network/       virtual network and subnets of one environment (issue #20)
environments/   one folder per environment, each calling the modules above
  dev/
  test/
  prod/
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

## Running an environment

```bash
cd environments/dev
terraform init
terraform plan -out=plan.tfplan
```

`terraform apply` is not part of this issue's scope: there is no Azure
subscription wired up yet, and the CI/CD pipeline that will run `plan` and
`apply` with OIDC and an approval gate is issue #23.

## Modules

- [`modules/network`](modules/network/README.md): virtual network and
  subnets for one environment, from `frioandes-platform/planning` issue #8.

## Related planning issues

- [#8](https://github.com/frioandes-platform/planning/issues/8) network topology and the verified IP plan this module reads.
- [#20](https://github.com/frioandes-platform/planning/issues/20) this repository and the network module.
- [#21](https://github.com/frioandes-platform/planning/issues/21) the security module, checked against the firewall policy table.
- [#23](https://github.com/frioandes-platform/planning/issues/23) the CI/CD pipeline that will plan and apply these environments.
