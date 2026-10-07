output "vnet_id" {
  description = "ID of the environment virtual network."
  value       = azurerm_virtual_network.this.id
}

output "vnet_name" {
  description = "Name of the environment virtual network."
  value       = azurerm_virtual_network.this.name
}

output "subnet_ids" {
  description = "Subnet ID by subnet name."
  value       = { for name, subnet in azurerm_subnet.this : name => subnet.id }
}

output "subnet_cidrs" {
  description = "Address prefix by subnet name, as verified in data/ip-plan.csv."
  value       = { for name, row in local.subnets : name => row.cidr }
}
