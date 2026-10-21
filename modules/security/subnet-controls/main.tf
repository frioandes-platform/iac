variable "environment" {
  description = "Application environment whose subnet NSGs are managed by this root."
  type        = string
  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "Select dev, test or prod."
  }
}
variable "resource_group_name" {
  type        = string
  description = "Application RG in the SAME subscription as the subnets."
}
variable "location" {
  type        = string
  description = "Application environment region."
}
variable "tags" {
  type        = map(string)
  description = "Governance tags."
}
variable "subnet_ids" {
  type        = map(string)
  description = "Output of modules/network for this environment."
}
variable "token_values" {
  type        = map(list(string))
  default     = {}
  description = "Whole CSV token replacements for approved IP addresses."
  validation {
    condition = alltrue([for key in keys(var.token_values) : strcontains(key, "<") && strcontains(key, ">")]) && alltrue([
      for values in values(var.token_values) : length(values) > 0 && alltrue([
        for value in values : trimspace(value) != "" && !contains(["*", "0.0.0.0/0", "::/0"], value) && !strcontains(value, "<") && !strcontains(value, ">")
      ])
    ])
    error_message = "Token replacements must be resolved nonempty values without an unrestricted wildcard."
  }
}
variable "active_temporary_rule_ids" {
  type        = set(string)
  default     = []
  description = "Explicit NSG temporary IDs still required during migration."
}
variable "migration_change_reference" {
  type        = string
  default     = ""
  description = "Approval reference when temporary NSG rules are selected."
}

locals {
  source_manifest = jsondecode(file("${path.module}/../data/source.json"))
  plan_rows       = csvdecode(file("${path.module}/../data/ip-plan.csv"))
  subnet_names    = toset([for row in local.plan_rows : row.subnet if row.env == var.environment])
  rows = {
    for row in csvdecode(file("${path.module}/../data/firewall-policy.csv")) : row.id => row
    if row.punto_control == "nsg" && row.ambiente == var.environment
  }
  active = { for id, row in local.rows : id => row if row.vigencia == "estable" || contains(var.active_temporary_rule_ids, id) }
  expanded_rules = merge({}, [
    for id, row in local.active : {
      for subnet in(row.grupo == "nsg todas las subredes" ? local.subnet_names : toset([trimprefix(row.grupo, "nsg ")])) : "${id}:${subnet}" => {
        id           = id
        subnet       = subnet
        direction    = row.tipo == "nsg-salida" ? "Outbound" : "Inbound"
        action       = row.accion == "Permitir" ? "Allow" : "Deny"
        protocol     = row.protocolo == "Cualquiera" ? "*" : title(lower(row.protocolo))
        ports        = [for token in split(" ", row.puertos) : token == "any" ? "*" : token]
        sources      = flatten([for token in split(" ", row.origen_rangos) : lookup(var.token_values, token, [token == "any" ? "*" : token == "internet" ? "Internet" : trimprefix(token, "tag:")])])
        destinations = [for token in split(" ", row.destino_rangos) : token == "any" ? "*" : trimprefix(token, "tag:")]
        priority     = row.accion == "Denegar" ? 4000 : 100 + tonumber(element(reverse(split("-", id)), 0)) * 10
        temporary    = row.vigencia == "temporal"
        retirement   = row.se_retira
      }
    }
  ]...)
  unresolved = distinct(flatten([for rule in values(local.expanded_rules) : [for token in rule.sources : token if strcontains(token, "<")]]))
}

resource "azurerm_network_security_group" "this" {
  for_each            = local.subnet_names
  name                = "nsg-fa-${var.environment}-${each.key}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags
  lifecycle {
    precondition {
      condition     = toset(keys(var.subnet_ids)) == local.subnet_names
      error_message = "The network module's subnet IDs must match the pinned security address plan."
    }
    precondition {
      condition     = alltrue([for filename, source in local.source_manifest.files : filesha256("${path.module}/../data/${filename}") == source.sha256])
      error_message = "Security source checksum mismatch."
    }
    precondition {
      condition     = length(local.unresolved) == 0
      error_message = "Resolve approved source IP placeholders before planning NSGs."
    }
    precondition {
      condition = (
        length(setsubtract(var.active_temporary_rule_ids, toset([for id, row in local.rows : id if row.vigencia == "temporal"]))) == 0 &&
        (length(var.active_temporary_rule_ids) == 0 || trimspace(var.migration_change_reference) != "")
      )
      error_message = "Temporary NSG IDs require valid scope and an approved change reference."
    }
  }
}

resource "azurerm_network_security_rule" "this" {
  for_each                     = local.expanded_rules
  name                         = "${each.value.temporary ? "temporary" : "stable"}-${each.value.id}"
  description                  = substr(each.value.temporary ? "TEMPORARY; retire: ${each.value.retirement}" : "STABLE; source: ${each.value.id}", 0, 140)
  priority                     = each.value.priority
  direction                    = each.value.direction
  access                       = each.value.action
  protocol                     = each.value.protocol
  source_port_range            = "*"
  destination_port_range       = length(each.value.ports) == 1 ? each.value.ports[0] : null
  destination_port_ranges      = length(each.value.ports) > 1 ? each.value.ports : null
  source_address_prefix        = length(each.value.sources) == 1 ? each.value.sources[0] : null
  source_address_prefixes      = length(each.value.sources) > 1 ? each.value.sources : null
  destination_address_prefix   = length(each.value.destinations) == 1 ? each.value.destinations[0] : null
  destination_address_prefixes = length(each.value.destinations) > 1 ? each.value.destinations : null
  resource_group_name          = var.resource_group_name
  network_security_group_name  = azurerm_network_security_group.this[each.value.subnet].name
}

resource "azurerm_subnet_network_security_group_association" "this" {
  for_each                  = local.subnet_names
  subnet_id                 = var.subnet_ids[each.key]
  network_security_group_id = azurerm_network_security_group.this[each.key].id
}

output "rule_ids" {
  description = "Source table IDs instantiated for this environment."
  value       = sort(keys(local.active))
}

output "nsg_ids" {
  description = "NSG IDs keyed by subnet name."
  value       = { for name, nsg in azurerm_network_security_group.this : name => nsg.id }
}
