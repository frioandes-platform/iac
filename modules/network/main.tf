resource "azurerm_virtual_network" "this" {
  name                = local.vnet_name
  address_space       = [local.vnet_cidr]
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_subnet" "this" {
  for_each = local.subnets

  name                 = each.key
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [each.value.cidr]

  private_endpoint_network_policies = contains(local.private_endpoint_services, each.value.service) ? "Disabled" : "Enabled"

  dynamic "delegation" {
    for_each = contains(keys(local.delegations), each.value.service) ? [local.delegations[each.value.service]] : []

    content {
      name = "delegation"

      service_delegation {
        name    = delegation.value.name
        actions = delegation.value.actions
      }
    }
  }
}
