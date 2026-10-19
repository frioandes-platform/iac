locals {
  source_manifest = jsondecode(file("${path.module}/data/source.json"))
  ip_plan_path    = "${path.module}/data/ip-plan.terraform.csv"
  ip_plan         = csvdecode(file(local.ip_plan_path))
  environment_rows = [
    for row in local.ip_plan : row
    if row.env == var.environment && row.category != "reserva"
  ]
  vnet_names = distinct([for row in local.environment_rows : row.vnet])
  vnet_cidrs = distinct([for row in local.environment_rows : row.vnet_cidr])
  subnets    = { for row in local.environment_rows : row.subnet => row }

  # Service names come from the reviewed Container Apps address plan.
  delegations = {
    container-apps-workload-profiles = "Microsoft.App/environments"
    functions-flex                   = "Microsoft.App/environments"
    mysql-flexible                   = "Microsoft.DBforMySQL/flexibleServers"
    fabric-vnet-gateway              = "Microsoft.PowerPlatform/vnetaccesslinks"
  }
  supported_services = concat(keys(local.delegations), [
    "app-gateway-v2", "private-endpoints", "admin-agents", "migration-tools"
  ])
}

resource "azurerm_virtual_network" "this" {
  name                = one(local.vnet_names)
  address_space       = local.vnet_cidrs
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  lifecycle {
    precondition {
      condition = (
        filesha256("${path.module}/data/ip-plan.csv") == local.source_manifest.files["ip-plan.csv"].sha256 &&
        filesha256(local.ip_plan_path) == local.source_manifest.derived["ip-plan.terraform.csv"].sha256
      )
      error_message = "The address plan checksum differs from source.json. Review the planning snapshot before using it."
    }
    precondition {
      condition     = length(local.vnet_names) == 1 && length(local.vnet_cidrs) == 1 && length(local.subnets) > 0
      error_message = "The selected environment must contain exactly one VNet and at least one subnet."
    }
    precondition {
      condition     = alltrue([for row in local.environment_rows : contains(local.supported_services, row.service)])
      error_message = "The snapshot includes an unsupported service. Review subnet delegations before planning."
    }
  }
}

resource "azurerm_subnet" "this" {
  for_each = local.subnets

  name                 = each.value.subnet
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [each.value.cidr]

  # Explicit egress is provided by the subsequent routing/security implementation.
  default_outbound_access_enabled = false

  # Archive migration bypasses Firewall routing but remains subject to NSGs (#8/#9).
  # Enabling a policy does not create an NSG or a route-table association.
  private_endpoint_network_policies = each.key == "snet-archive" ? "NetworkSecurityGroupEnabled" : "Enabled"

  dynamic "delegation" {
    for_each = contains(keys(local.delegations), each.value.service) ? [local.delegations[each.value.service]] : []
    content {
      name = "service-delegation"
      service_delegation {
        name    = delegation.value
        actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
      }
    }
  }
}
