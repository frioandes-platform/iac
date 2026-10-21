variable "enable_eventhub_private_dns" {
  description = "Create the ONE shared Event Hubs DNS zone for #22. Reuse/import an existing zone instead of duplicating it."
  type        = bool
  default     = false
}

variable "eventhub_dns_spoke_vnet_ids" {
  description = "Environment labels to existing network.vnet_id outputs. Links use IDs, never copied address ranges."
  type        = map(string)
  default     = {}
  validation {
    condition     = alltrue([for env in keys(var.eventhub_dns_spoke_vnet_ids) : contains(["dev", "test", "prod"], env)])
    error_message = "Only approved application environments may link to the shared zone."
  }
}

resource "azurerm_private_dns_zone" "eventhub" {
  count               = var.enable_eventhub_private_dns ? 1 : 0
  name                = "privatelink.servicebus.windows.net"
  resource_group_name = azurerm_resource_group.connectivity.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "eventhub_hub" {
  count                 = var.enable_eventhub_private_dns ? 1 : 0
  name                  = "eventhubs-hub"
  resource_group_name   = azurerm_resource_group.connectivity.name
  private_dns_zone_name = azurerm_private_dns_zone.eventhub[0].name
  virtual_network_id    = azurerm_virtual_network.hub.id
  registration_enabled  = false
  tags                  = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "eventhub_spoke" {
  for_each              = var.enable_eventhub_private_dns ? var.eventhub_dns_spoke_vnet_ids : {}
  name                  = "eventhubs-${each.key}"
  resource_group_name   = azurerm_resource_group.connectivity.name
  private_dns_zone_name = azurerm_private_dns_zone.eventhub[0].name
  virtual_network_id    = each.value
  registration_enabled  = false
  tags                  = local.tags
}

output "eventhub_private_dns" {
  description = "Shared zone and VNet links to pass to subsequent application-root invocations."
  value = var.enable_eventhub_private_dns ? {
    zone_id        = azurerm_private_dns_zone.eventhub[0].id
    spoke_link_ids = { for name, link in azurerm_private_dns_zone_virtual_network_link.eventhub_spoke : name => link.id }
  } : null
}
