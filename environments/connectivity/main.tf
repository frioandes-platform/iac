locals {
  rows             = csvdecode(file("${path.module}/../../modules/security/data/ip-plan.csv"))
  hub_rows         = [for row in local.rows : row if row.env == "hub"]
  hub_name         = one(distinct([for row in local.hub_rows : row.vnet]))
  hub_cidr         = one(distinct([for row in local.hub_rows : row.vnet_cidr]))
  firewall_subnets = { for row in local.hub_rows : row.subnet => row if contains(["firewall", "firewall-management"], row.service) }
  tags = {
    ambiente    = "shared"
    carga       = "red"
    costo       = "compartido"
    criticidad  = "alta"
    responsable = var.owner_team
  }
}
resource "azurerm_resource_group" "connectivity" {
  name     = "rg-fa-connectivity"
  location = var.location
  tags     = local.tags
}
resource "azurerm_virtual_network" "hub" {
  name                = local.hub_name
  address_space       = [local.hub_cidr]
  location            = var.location
  resource_group_name = azurerm_resource_group.connectivity.name
  tags                = local.tags
}
resource "azurerm_subnet" "firewall" {
  # checkov:skip=CKV2_AZURE_31:Azure does not allow an NSG on AzureFirewallSubnet or AzureFirewallManagementSubnet.
  for_each                        = local.firewall_subnets
  name                            = each.key
  address_prefixes                = [each.value.cidr]
  resource_group_name             = azurerm_resource_group.connectivity.name
  virtual_network_name            = azurerm_virtual_network.hub.name
  default_outbound_access_enabled = false
}
module "security" {
  source                     = "../../modules/security"
  resource_group_name        = azurerm_resource_group.connectivity.name
  location                   = var.location
  tags                       = local.tags
  firewall_subnet_id         = azurerm_subnet.firewall["AzureFirewallSubnet"].id
  management_subnet_id       = azurerm_subnet.firewall["AzureFirewallManagementSubnet"].id
  environments               = var.protected_environments
  token_values               = var.security_token_values
  active_temporary_rule_ids  = var.active_temporary_firewall_rules
  migration_change_reference = var.migration_change_reference
}
output "firewall_private_ip" { value = module.security.firewall_private_ip }
output "firewall_id" { value = module.security.firewall_id }
