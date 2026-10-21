output "namespace_id" {
  description = "Namespace ID; another reviewed event hub can reuse this namespace."
  value       = azurerm_eventhub_namespace.this.id
}
output "namespace_fqdn" {
  description = "Use the normal service FQDN; shared private DNS resolves it privately."
  value       = "${azurerm_eventhub_namespace.this.name}.servicebus.windows.net"
}
output "eventhub_id" {
  description = "Alerts event hub ID, also the least-privilege data role scope."
  value       = azurerm_eventhub.alerts.id
}
output "eventhub_name" {
  description = "Event hub consumed by the future telemetry notifier."
  value       = azurerm_eventhub.alerts.name
}
output "consumer_group_name" {
  description = "Independent notifier checkpoint/offset group."
  value       = azurerm_eventhub_consumer_group.notifier.name
}
output "private_endpoint_id" {
  description = "Private endpoint ID for deployment verification."
  value       = azurerm_private_endpoint.this.id
}
output "integration" {
  description = "Configured resource properties for integration assertions; not runtime reachability evidence."
  value = {
    subnet_id             = azurerm_private_endpoint.this.subnet_id
    nsg_id                = var.security.nsg_id
    private_dns_zone_ids  = azurerm_private_endpoint.this.private_dns_zone_group[0].private_dns_zone_ids
    public_access_enabled = azurerm_eventhub_namespace.this.public_network_access_enabled
    local_auth_enabled    = azurerm_eventhub_namespace.this.local_authentication_enabled
    tls_version           = azurerm_eventhub_namespace.this.minimum_tls_version
    sku                   = azurerm_eventhub_namespace.this.sku
    capacity              = azurerm_eventhub_namespace.this.capacity
    retention_days        = azurerm_eventhub.alerts.message_retention
    sender_scopes         = { for key, role in azurerm_role_assignment.sender : key => role.scope }
    receiver_scopes       = { for key, role in azurerm_role_assignment.receiver : key => role.scope }
  }
}
