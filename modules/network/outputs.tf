output "vnet_id" {
  description = "VNet resource ID for future peering and security modules."
  value       = azurerm_virtual_network.this.id
}

output "vnet_name" {
  description = "VNet name taken from the approved plan."
  value       = azurerm_virtual_network.this.name
}

output "address_space" {
  description = "VNet prefixes taken from the approved plan."
  value       = azurerm_virtual_network.this.address_space
}

output "subnet_ids" {
  description = "Subnet resource IDs keyed by approved subnet name."
  value       = { for name, subnet in azurerm_subnet.this : name => subnet.id }
}

output "subnet_prefixes" {
  description = "Configured subnet prefixes, used for plan verification."
  value       = { for name, subnet in azurerm_subnet.this : name => subnet.address_prefixes }
}

output "subnet_delegations" {
  description = "Configured service delegations keyed by subnet name."
  value = {
    for name, subnet in azurerm_subnet.this : name => [
      for item in subnet.delegation : item.service_delegation[0].name
    ]
  }
}

output "private_endpoint_network_policies" {
  description = "Private endpoint policy mode keyed by subnet name."
  value       = { for name, subnet in azurerm_subnet.this : name => subnet.private_endpoint_network_policies }
}
