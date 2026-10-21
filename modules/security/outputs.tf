output "firewall_id" {
  description = "ID of the shared connectivity firewall."
  value       = azurerm_firewall.this.id
}

output "firewall_private_ip" {
  description = "Next hop for the later reviewed route-table implementation."
  value       = azurerm_firewall.this.ip_configuration[0].private_ip_address
}

output "egress_public_ips" {
  description = "Egress addresses; management uses a separate platform IP."
  value       = [for ip in azurerm_public_ip.egress : ip.ip_address]
}

output "selected_rule_ids" {
  description = "Explicit table IDs represented in active collections. FW-999 is implicit."
  value       = sort(keys(local.selected))
}

output "temporary_rule_register" {
  description = "Retirement conditions remain visible even when temporary rules are disabled."
  value = {
    for id, row in local.firewall_rows : id => {
      active       = contains(var.active_temporary_rule_ids, id)
      retirement   = row.se_retira
      source_group = row.grupo
    } if row.vigencia == "temporal"
  }
}

output "implicit_deny" {
  description = "FW-999 is default denial after application-rule processing; NEVER an explicit catch-all network deny."
  value       = "FW-999: implicit deny; platform infrastructure rules and stateful return traffic retain Azure semantics."
}
