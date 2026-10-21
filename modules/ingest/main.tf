resource "azurerm_eventhub_namespace" "this" {
  name                          = var.namespace_name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  sku                           = "Standard"
  capacity                      = 1
  auto_inflate_enabled          = false
  public_network_access_enabled = false
  local_authentication_enabled  = false
  minimum_tls_version           = "1.2"
  tags                          = var.tags

  network_rulesets {
    default_action                = "Deny"
    public_network_access_enabled = false
    # Planning #13 sections 3.2/5.2: Stream Analytics uses Entra + this exception.
    # Network bypass never grants a data-plane role to an arbitrary service.
    trusted_service_access_enabled = true
  }

  lifecycle {
    precondition {
      condition     = lower(var.network.subnet_id) == "${lower(var.network.vnet_id)}/subnets/snet-data-pe"
      error_message = "Event Hubs belongs in snet-data-pe of the referenced application VNet, not snet-ingest."
    }
    precondition {
      condition     = contains(["Enabled", "NetworkSecurityGroupEnabled"], var.network.private_endpoint_network_policies)
      error_message = "Private endpoint NSG enforcement must remain enabled."
    }
    precondition {
      condition = (
        trimspace(var.security.nsg_id) != "" &&
        contains(var.security.rule_ids, "NSG-${var.environment}-${var.environment == "prod" ? "17" : "13"}") &&
        contains(var.security.rule_ids, "NSG-${var.environment}-99")
      )
      error_message = "Pass the existing data-subnet NSG and its notifier allow/default-deny table IDs."
    }
  }
}

resource "azurerm_eventhub" "alerts" {
  name              = "alerts"
  namespace_id      = azurerm_eventhub_namespace.this.id
  partition_count   = 2
  message_retention = 7
  status            = "Active"
}

resource "azurerm_eventhub_consumer_group" "notifier" {
  name                = "notifier"
  namespace_name      = azurerm_eventhub_namespace.this.name
  eventhub_name       = azurerm_eventhub.alerts.name
  resource_group_name = var.resource_group_name
}

resource "azurerm_eventhub_consumer_group" "verification" {
  count               = var.environment == "dev" ? 1 : 0
  name                = "verification"
  namespace_name      = azurerm_eventhub_namespace.this.name
  eventhub_name       = azurerm_eventhub.alerts.name
  resource_group_name = var.resource_group_name
}

resource "azurerm_private_endpoint" "this" {
  name                = "pe-${var.namespace_name}"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.network.subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "eventhubs"
    private_connection_resource_id = azurerm_eventhub_namespace.this.id
    subresource_names              = ["namespace"]
    is_manual_connection           = false
  }
  private_dns_zone_group {
    name                 = "eventhubs"
    private_dns_zone_ids = [var.private_dns_zone_id]
  }
}

resource "azurerm_role_assignment" "sender" {
  for_each             = var.sender_principal_ids
  scope                = azurerm_eventhub.alerts.id
  role_definition_name = "Azure Event Hubs Data Sender"
  principal_id         = each.value
}

resource "azurerm_role_assignment" "receiver" {
  for_each             = var.receiver_principal_ids
  scope                = azurerm_eventhub.alerts.id
  role_definition_name = "Azure Event Hubs Data Receiver"
  principal_id         = each.value
}
