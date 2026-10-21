mock_provider "azurerm" {
  mock_resource "azurerm_eventhub_namespace" {
    defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.EventHub/namespaces/fa-alerts-dev-test" }
  }
  mock_resource "azurerm_eventhub" {
    defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.EventHub/namespaces/fa-alerts-dev-test/eventhubs/alerts" }
  }
  mock_resource "azurerm_network_security_group" {
    defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/networkSecurityGroups/nsg-fa-dev-snet-data-pe" }
  }
}

run "disabled_by_default" {
  command = plan
  variables {
    security_token_values = jsondecode(file("../../tests/fixtures/security-tokens.json"))
  }
  assert {
    condition     = length(module.ingest) == 0
    error_message = "Existing network/security roots must not silently create a workload."
  }
}

# apply is exclusively in the mocked test state; it does not call Azure.
run "private_alert_ingest_uses_existing_modules" {
  command = apply
  variables {
    security_token_values = jsondecode(file("../../tests/fixtures/security-tokens.json"))
    ingest = {
      namespace_name         = "fa-alerts-dev-test"
      private_dns_zone_id    = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-connectivity/providers/Microsoft.Network/privateDnsZones/privatelink.servicebus.windows.net"
      sender_principal_ids   = { simulator = "11111111-1111-1111-1111-111111111111" }
      receiver_principal_ids = { notifier = "22222222-2222-2222-2222-222222222222" }
    }
  }
  override_resource {
    target = module.network.azurerm_virtual_network.this
    values = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-dev" }
  }
  override_resource {
    target = module.network.azurerm_subnet.this["snet-ingress"]
    values = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-dev/subnets/snet-ingress" }
  }
  override_resource {
    target = module.network.azurerm_subnet.this["snet-app-torre"]
    values = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-dev/subnets/snet-app-torre" }
  }
  override_resource {
    target = module.network.azurerm_subnet.this["snet-app-portal"]
    values = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-dev/subnets/snet-app-portal" }
  }
  override_resource {
    target = module.network.azurerm_subnet.this["snet-data"]
    values = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-dev/subnets/snet-data" }
  }
  override_resource {
    target = module.network.azurerm_subnet.this["snet-data-pe"]
    values = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-dev/subnets/snet-data-pe" }
  }
  override_resource {
    target = module.network.azurerm_subnet.this["snet-archive"]
    values = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-dev/subnets/snet-archive" }
  }
  override_resource {
    target = module.network.azurerm_subnet.this["snet-ingest"]
    values = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-dev/subnets/snet-ingest" }
  }
  override_resource {
    target = module.network.azurerm_subnet.this["snet-admin"]
    values = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-dev/subnets/snet-admin" }
  }
  override_resource {
    target = module.network.azurerm_subnet.this["snet-cali-integration"]
    values = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-dev/subnets/snet-cali-integration" }
  }
  override_resource {
    target = module.network.azurerm_subnet.this["snet-fabric-egress"]
    values = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-dev/subnets/snet-fabric-egress" }
  }
  override_resource {
    target = module.network.azurerm_subnet.this["snet-telemetry-func"]
    values = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-dev/subnets/snet-telemetry-func" }
  }
  assert {
    condition     = module.ingest["alerts"].integration.subnet_id == module.network.subnet_ids["snet-data-pe"] && module.ingest["alerts"].integration.nsg_id == module.subnet_security.nsg_ids["snet-data-pe"]
    error_message = "Ingest must consume the existing network and security module references."
  }
  assert {
    condition     = !module.ingest["alerts"].integration.public_access_enabled && !module.ingest["alerts"].integration.local_auth_enabled && module.ingest["alerts"].integration.tls_version == "1.2"
    error_message = "Public access and SAS must remain disabled and TLS 1.2 required."
  }
  assert {
    condition     = toset(module.ingest["alerts"].integration.private_dns_zone_ids) == toset([var.ingest.private_dns_zone_id])
    error_message = "Reuse the shared DNS zone instead of creating an isolated zone."
  }
  assert {
    condition     = module.ingest["alerts"].integration.sku == "Standard" && module.ingest["alerts"].integration.capacity == 1 && module.ingest["alerts"].integration.retention_days == 7
    error_message = "The representative alert buffer must match the documented baseline."
  }
  assert {
    condition     = module.ingest["alerts"].integration.sender_scopes["simulator"] == module.ingest["alerts"].eventhub_id && module.ingest["alerts"].integration.receiver_scopes["notifier"] == module.ingest["alerts"].eventhub_id
    error_message = "Data roles must be scoped to the alert event hub, not the subscription."
  }
}
