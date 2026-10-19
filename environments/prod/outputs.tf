output "vnet_id" {
  description = "VNet ID for subsequent infrastructure modules."
  value       = module.network.vnet_id
}

output "subnet_ids" {
  description = "Subnet IDs keyed by approved name for security and workload modules."
  value       = module.network.subnet_ids
}
