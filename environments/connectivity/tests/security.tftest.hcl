mock_provider "azurerm" {}
variables {
  security_token_values = jsondecode(file("../../tests/fixtures/security-tokens.json"))
}
run "development_stable_policy" {
  command = plan
  assert {
    condition     = length(module.security.selected_rule_ids) == 11
    error_message = "Expected 11 explicit stable development firewall rules."
  }
  assert {
    condition     = length([for rule in values(module.security.temporary_rule_register) : rule if rule.active]) == 0
    error_message = "Migration access must not be silently enabled."
  }
}
run "all_environments_stable_policy" {
  command = plan
  variables { protected_environments = ["dev", "test", "prod"] }
  assert {
    condition     = length(module.security.selected_rule_ids) == 34
    error_message = "Expected 34 explicit stable firewall rules across three environments."
  }
}
run "migration_explicitly_selected" {
  command = plan
  variables {
    protected_environments          = ["dev", "test", "prod"]
    active_temporary_firewall_rules = ["FW-401", "FW-402", "FW-501", "FW-502", "FW-503", "FW-504"]
    migration_change_reference      = "MOCK-CHANGE-ONLY"
  }
  assert {
    condition     = length(module.security.selected_rule_ids) == 40
    error_message = "Expected 34 stable and six explicitly selected temporary rules."
  }
}
