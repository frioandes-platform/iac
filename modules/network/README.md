# Application network module

Creates one Azure VNet and every subnet in the approved Container Apps address
plan for `dev`, `test` or `prod`. The selected environment is the only address
selector. `hub` and reservation rows are never instantiated.

## Source and provenance

Repository: [`frioandes-platform/planning`](https://github.com/frioandes-platform/planning).
Source commit: `739be496705504a270ed499d792d0897214bb48e`.
Design: [issue #8](https://github.com/frioandes-platform/planning/issues/8).

| Vendored file | Source path | SHA-256 at copy time |
|---|---|---|
| `data/ip-plan.csv` | `docs/architecture/red/data/ip-plan.csv` | `d55eabf7c7be8e5d0d751e01885f4794fed8b0efe54374c285825ad517f8660b` |
| `data/onprem-inventory.csv` | `docs/architecture/red/data/onprem-inventory.csv` | `7bdcd686c47174dc14c23e9b545ac15832902996054e795f2eeae03451876d9e` |

Terraform reads `data/ip-plan.terraform.csv`, generated reproducibly by
`python3 scripts/prepare_network_data.py`. The upstream CSV has three rows
with unquoted commas in the trailing notes. The generator merges only those
known notes fields and writes strict CSV. All names, CIDRs and other first
nine fields remain unchanged. The original files and their hashes above remain
intact; the derived SHA-256 is recorded separately in `data/source.json`.
The verifier compares the derived bytes with the expected transformation and
checks every row has the header field count. Unknown malformed rows fail.

The source Git blob IDs are `82a90fb7ad8c324399ed82a4f5e5258f5fc3bf06` and
`e9c6c876b22d5a882c8d4c201d3d977bde7ebb70`, respectively. These match the
original remote files. `data/source.json` stores machine-readable provenance.
The on-premises inventory is used by the repository verifier, not to create
on-premises networks. Preserve the Spanish CSV content exactly.

## Resources and service configuration

The module uses `for_each` keyed by subnet name. Reordering the CSV therefore
does not change Terraform resource addresses. It does not mix inline VNet
subnets with standalone `azurerm_subnet` resources.

| Subnet | Configuration |
|---|---|
| `snet-ingress` | Dedicated Application Gateway v2 subnet; no delegation in this selected design |
| `snet-app-torre`, `snet-app-portal` | Delegated separately to `Microsoft.App/environments` |
| `snet-data` | Delegated to `Microsoft.DBforMySQL/flexibleServers` |
| `snet-data-pe` | Private endpoint subnet, no delegation |
| `snet-archive` | Private endpoint subnet; `NetworkSecurityGroupEnabled` policy mode |
| `snet-ingest` | Private endpoints for ingestion, no delegation |
| `snet-admin` | Administration and agent subnet |
| `snet-cali-integration` | Migration subnet, no delegation in the approved plan |
| `snet-fabric-egress` | Delegated to `Microsoft.PowerPlatform/vnetaccesslinks` |
| `snet-telemetry-func` | Separate Functions Flex subnet delegated to `Microsoft.App/environments` |

All other subnets use `Enabled` for private endpoint network policies. These
settings enable subsequent NSG/route enforcement; they do not create the NSGs,
routes, endpoints or services. Archive keeps NSG-only policies to preserve the
reviewed migration routing exception. Service delegation actions use subnet
`join/action`; verify the regional service requirements before deployment.

Default outbound access is explicitly disabled. Explicit outbound routing and
security are prerequisites for future workloads. DNS uses Azure's default at
this network-only stage; hub peering and the final hybrid resolver configuration
must be integrated before using on-premises/private application resolution.
No operational isolation or complete hybrid connectivity is claimed here.

## Inputs

| Name | Type | Required | Purpose |
|---|---|---|---|
| `environment` | string | yes | `dev`, `test` or `prod`; selects approved rows |
| `resource_group_name` | string | yes | Existing/parent-managed resource group |
| `location` | string | yes | Approved Azure location |
| `tags` | map(string) | yes | Governance tags for the VNet |

Subnets do not support Azure tags. The environment root applies the governance
tags to its resource group and passes the same tags to the VNet.

## Outputs

`vnet_id`, `vnet_name`, `address_space`, `subnet_ids`, `subnet_prefixes`,
`subnet_delegations`, `private_endpoint_network_policies`.
Security modules should consume `subnet_ids` rather than reconstructing resource IDs.

## Usage

Call this module from an environment root, as already implemented in
`environments/dev`, `environments/test` and `environments/prod`:

```hcl
module "network" {
  source = "../../modules/network"

  environment         = local.environment
  resource_group_name = azurerm_resource_group.network.name
  location            = azurerm_resource_group.network.location
  tags                = local.tags
}
```

Do not run `plan` or `apply` directly in this module. See the repository README
for offline checks, mocked tests, later authenticated plans and snapshot updates.

## Technical references

- [AzureRM 4.62.0 subnet schema](https://registry.terraform.io/providers/hashicorp/azurerm/4.62.0/docs/resources/subnet)
- [AzureRM virtual network](https://registry.terraform.io/providers/hashicorp/azurerm/4.62.0/docs/resources/virtual_network)
- [Terraform provider mocking](https://developer.hashicorp.com/terraform/language/tests/mocking)
