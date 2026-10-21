locals {
  source_manifest = jsondecode(file("${path.module}/data/source.json"))
  policy_rows     = csvdecode(file("${path.module}/data/firewall-policy.csv"))
  settings        = { for row in csvdecode(file("${path.module}/data/firewall-settings.csv")) : row.clave => row.valor }
  firewall_rows = {
    for row in local.policy_rows : row.id => row
    if row.punto_control == "azure-firewall" && row.id != "FW-999" && (
      contains(var.environments, row.ambiente) || row.ambiente == "hub"
    )
  }
  temporary_ids = toset([for id, row in local.firewall_rows : id if row.vigencia == "temporal"])
  selected = {
    for id, row in local.firewall_rows : id => row
    if row.vigencia == "estable" || contains(var.active_temporary_rule_ids, id)
  }
  resolved = {
    for id, row in local.selected : id => {
      id          = id
      kind        = row.tipo
      action      = row.accion == "Permitir" ? "Allow" : "Deny"
      group       = split(" ", row.grupo)[0]
      group_name  = replace(row.grupo, " ", "-")
      temporary   = row.vigencia == "temporal"
      retirement  = row.se_retira
      environment = row.ambiente
      sources = flatten([
        for token in split(" ", row.origen_rangos) : lookup(var.token_values, token, [token == "any" ? "*" : trimprefix(token, "tag:")])
      ])
      destinations = flatten([
        for token in split(" ", row.destino_rangos) : lookup(var.token_values, token, [trimprefix(trimprefix(token, "fqdn:"), "tag:")])
      ])
      ports     = flatten([for token in split(" ", row.puertos) : lookup(var.token_values, token, [token])])
      protocols = row.tipo == "red" ? split(" ", row.protocolo) : []
      # Pair each application protocol with its port; do not form a cross product.
      application_protocols = row.tipo == "aplicacion" ? [
        for protocol in split(" ", row.protocolo) : {
          type = protocol == "HTTPS" ? "Https" : "Http"
          port = protocol == "HTTPS" ? 443 : 80
        }
      ] : []
    }
  }
  groups = { for group in distinct([for rule in values(local.resolved) : rule.group]) : group => {
    name      = one(distinct([for rule in values(local.resolved) : rule.group_name if rule.group == group]))
    temporary = tonumber(group) >= 400
  } }
  unresolved_tokens = distinct(flatten([
    for rule in values(local.resolved) : [for token in concat(rule.sources, rule.destinations, rule.ports) : token if strcontains(token, "<") || strcontains(token, ">")]
  ]))
}

resource "azurerm_public_ip" "egress" {
  count               = tonumber(local.settings.public_ip_count)
  name                = "${var.name}-egress-${count.index + 1}"
  location            = var.location
  resource_group_name = var.resource_group_name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = var.tags
}

resource "azurerm_public_ip" "management" {
  name                = "${var.name}-management"
  location            = var.location
  resource_group_name = var.resource_group_name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = var.tags
}

resource "azurerm_firewall_policy" "this" {
  name                              = "${var.name}-policy"
  resource_group_name               = var.resource_group_name
  location                          = var.location
  sku                               = local.settings.sku_tier
  threat_intelligence_mode          = local.settings.threat_intel_mode == "Alert and Deny" ? "Deny" : "Alert"
  private_ip_ranges                 = split(" ", local.settings.snat_private_ranges)
  auto_learn_private_ranges_enabled = false
  tags                              = var.tags

  dns {
    proxy_enabled = local.settings.dns_proxy != "Desactivado"
  }

  lifecycle {
    precondition {
      condition     = alltrue([for filename, source in local.source_manifest.files : filesha256("${path.module}/data/${filename}") == source.sha256])
      error_message = "Security source snapshot checksum mismatch. Review the pinned planning files."
    }
    precondition {
      condition = (
        local.settings.sku_tier == "Standard" &&
        local.settings.threat_intel_mode == "Alert and Deny" &&
        local.settings.dns_proxy == "Desactivado" &&
        tonumber(local.settings.public_ip_count) == 1 &&
        alltrue([for row in values(local.selected) : contains(["red", "aplicacion"], row.tipo) && row.accion == "Permitir"]) &&
        alltrue([for row in values(local.selected) : alltrue([
          for protocol in split(" ", row.protocolo) : contains(row.tipo == "red" ? ["TCP", "UDP", "ICMP", "Any"] : ["HTTP", "HTTPS"], protocol)
        ])])
      )
      error_message = "The reviewed Container Apps security settings changed. Review the translator before planning."
    }
    precondition {
      condition     = length(local.unresolved_tokens) == 0
      error_message = "Resolve each selected CSV placeholder through token_values before planning: ${join(", ", local.unresolved_tokens)}"
    }
    precondition {
      condition     = length(setsubtract(var.active_temporary_rule_ids, local.temporary_ids)) == 0
      error_message = "A temporary rule ID is unknown or belongs to an unselected environment."
    }
    precondition {
      condition     = length(var.active_temporary_rule_ids) == 0 || trimspace(var.migration_change_reference) != ""
      error_message = "Temporary rules require an approved migration change reference."
    }
  }
}

resource "azurerm_firewall" "this" {
  name                = var.name
  location            = var.location
  resource_group_name = var.resource_group_name
  sku_name            = "AZFW_VNet"
  sku_tier            = local.settings.sku_tier
  firewall_policy_id  = azurerm_firewall_policy.this.id
  tags                = var.tags

  dynamic "ip_configuration" {
    for_each = azurerm_public_ip.egress
    content {
      name                 = "egress-${ip_configuration.key}"
      subnet_id            = ip_configuration.key == 0 ? var.firewall_subnet_id : null
      public_ip_address_id = ip_configuration.value.id
    }
  }
  management_ip_configuration {
    name                 = "management"
    subnet_id            = var.management_subnet_id
    public_ip_address_id = azurerm_public_ip.management.id
  }
}

resource "azurerm_firewall_policy_rule_collection_group" "this" {
  for_each = local.groups

  name               = "${each.value.temporary ? "temporary" : "stable"}-${each.value.name}"
  firewall_policy_id = azurerm_firewall_policy.this.id
  priority           = tonumber(each.key)

  dynamic "network_rule_collection" {
    for_each = { for id, rule in local.resolved : id => rule if rule.group == each.key && rule.kind == "red" }
    content {
      name     = "${network_rule_collection.value.temporary ? "temporary" : "stable"}-${network_rule_collection.key}"
      priority = tonumber(split("-", network_rule_collection.key)[1])
      action   = network_rule_collection.value.action
      rule {
        name                  = network_rule_collection.key
        description           = substr(network_rule_collection.value.temporary ? "TEMPORARY; retire: ${network_rule_collection.value.retirement}; change: ${var.migration_change_reference}" : "STABLE; source: ${network_rule_collection.key}", 0, 128)
        protocols             = network_rule_collection.value.protocols
        source_addresses      = network_rule_collection.value.sources
        destination_addresses = network_rule_collection.value.destinations
        destination_ports     = network_rule_collection.value.ports
      }
    }
  }

  dynamic "application_rule_collection" {
    for_each = { for id, rule in local.resolved : id => rule if rule.group == each.key && rule.kind == "aplicacion" }
    content {
      name     = "${application_rule_collection.value.temporary ? "temporary" : "stable"}-${application_rule_collection.key}"
      priority = tonumber(split("-", application_rule_collection.key)[1])
      action   = application_rule_collection.value.action
      rule {
        name              = application_rule_collection.key
        description       = substr(application_rule_collection.value.temporary ? "TEMPORARY; retire: ${application_rule_collection.value.retirement}; change: ${var.migration_change_reference}" : "STABLE; source: ${application_rule_collection.key}", 0, 128)
        source_addresses  = application_rule_collection.value.sources
        destination_fqdns = application_rule_collection.value.destinations
        terminate_tls     = false
        dynamic "protocols" {
          for_each = application_rule_collection.value.application_protocols
          content {
            type = protocols.value.type
            port = protocols.value.port
          }
        }
      }
    }
  }
}
