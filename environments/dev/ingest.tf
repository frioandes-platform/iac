variable "ingest" {
  description = "Opt-in representative workload for planning #22. DNS is supplied by connectivity outputs; no real sensors in dev."
  type = object({
    namespace_name         = string
    capacity               = optional(number, 1)
    private_dns_zone_id    = string
    sender_principal_ids   = optional(map(string), {})
    receiver_principal_ids = optional(map(string), {})
  })
  default = null
}

module "ingest" {
  source   = "../../modules/ingest"
  for_each = var.ingest == null ? {} : { alerts = var.ingest }

  environment         = local.environment
  namespace_name      = each.value.namespace_name
  capacity            = each.value.capacity
  resource_group_name = azurerm_resource_group.network.name
  location            = azurerm_resource_group.network.location
  tags                = merge(local.tags, { carga = "telemetria" })
  network = {
    vnet_id                           = module.network.vnet_id
    subnet_id                         = module.network.subnet_ids["snet-data-pe"]
    private_endpoint_network_policies = module.network.private_endpoint_network_policies["snet-data-pe"]
  }
  security = {
    nsg_id   = module.subnet_security.nsg_ids["snet-data-pe"]
    rule_ids = module.subnet_security.rule_ids
  }
  private_dns_zone_id    = each.value.private_dns_zone_id
  sender_principal_ids   = each.value.sender_principal_ids
  receiver_principal_ids = each.value.receiver_principal_ids

  # An NSG ID alone does not wait for its rules and subnet associations.
  depends_on = [module.subnet_security]
}

output "telemetry_alerts" {
  description = "Non-secret connection metadata; null when the workload is disabled."
  value = try({
    namespace_fqdn      = module.ingest["alerts"].namespace_fqdn
    eventhub_name       = module.ingest["alerts"].eventhub_name
    consumer_group      = module.ingest["alerts"].consumer_group_name
    eventhub_id         = module.ingest["alerts"].eventhub_id
    private_endpoint_id = module.ingest["alerts"].private_endpoint_id
  }, null)
}
