mock_provider "azurerm" {}
variables {
  security_token_values       = jsondecode(file("../../tests/fixtures/security-tokens.json"))
  enable_eventhub_private_dns = jsondecode(file("../../costs/inputs/connectivity.tfvars.json")).enable_eventhub_private_dns
  eventhub_dns_spoke_vnet_ids = jsondecode(file("../../costs/inputs/connectivity.tfvars.json")).eventhub_dns_spoke_vnet_ids
}
run "one_shared_zone_links_hub_and_dev" {
  command = plan
  assert {
    condition     = length(azurerm_private_dns_zone.eventhub) == 1 && azurerm_private_dns_zone.eventhub[0].name == "privatelink.servicebus.windows.net"
    error_message = "Own one Event Hubs DNS zone centrally."
  }
  assert {
    condition     = azurerm_private_dns_zone_virtual_network_link.eventhub_spoke["dev"].virtual_network_id == var.eventhub_dns_spoke_vnet_ids["dev"] && !azurerm_private_dns_zone_virtual_network_link.eventhub_spoke["dev"].registration_enabled
    error_message = "The application link must use the passed network output without autoregistration."
  }
  assert {
    condition     = length(azurerm_private_dns_zone_virtual_network_link.eventhub_hub) == 1 && !azurerm_private_dns_zone_virtual_network_link.eventhub_hub[0].registration_enabled
    error_message = "The shared zone must also be linked to the hub for hybrid resolution."
  }
}
