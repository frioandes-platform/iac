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

variables {
  environment         = "dev"
  namespace_name      = "fa-alerts-dev-test"
  resource_group_name = "rg-fa-network-dev"
  location            = "eastus2"
  tags                = {}
  network             = { "vnet_id" : "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-dev", "subnet_id" : "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-dev/subnets/snet-data-pe", "private_endpoint_network_policies" : "Enabled" }
  security            = { "nsg_id" : "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/networkSecurityGroups/nsg-fa-dev-snet-data-pe", "rule_ids" : ["NSG-dev-13", "NSG-dev-99"] }
  private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-connectivity/providers/Microsoft.Network/privateDnsZones/privatelink.servicebus.windows.net"
}

run "approved_alert_contract" {
  command = plan
  module { source = "../../modules/ingest" }
  assert {
    condition     = azurerm_eventhub_namespace.this.network_rulesets[0].default_action == "Deny" && azurerm_eventhub_namespace.this.network_rulesets[0].trusted_service_access_enabled
    error_message = "The Stream Analytics trusted-service exception must coexist with default denial."
  }
}

run "reject_sensor_subnet" {
  command = plan
  module { source = "../../modules/ingest" }
  variables {
    network = { "vnet_id" : "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-dev", "subnet_id" : "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-dev/subnets/snet-ingest", "private_endpoint_network_policies" : "Enabled" }
  }
  expect_failures = [azurerm_eventhub_namespace.this]
}

run "reject_disabled_nsg_enforcement" {
  command = plan
  module { source = "../../modules/ingest" }
  variables {
    network = { "vnet_id" : "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-dev", "subnet_id" : "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-dev/subnets/snet-data-pe", "private_endpoint_network_policies" : "Disabled" }
  }
  expect_failures = [azurerm_eventhub_namespace.this]
}

run "reject_missing_notifier_rule" {
  command = plan
  module { source = "../../modules/ingest" }
  variables {
    security = { "nsg_id" : "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-fa-network-dev/providers/Microsoft.Network/networkSecurityGroups/nsg-fa-dev-snet-data-pe", "rule_ids" : ["NSG-dev-99"] }
  }
  expect_failures = [azurerm_eventhub_namespace.this]
}
