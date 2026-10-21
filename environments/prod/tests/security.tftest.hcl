mock_provider "azurerm" {}
variables {
  security_token_values = jsondecode(file("../../tests/fixtures/security-tokens.json"))
}
run "subnet_policy_matches_table" {
  command = plan
  assert {
    condition = toset(module.subnet_security.rule_ids) == toset([
      for row in csvdecode(file("../../modules/security/data/firewall-policy.csv")) : row.id
      if row.punto_control == "nsg" && row.ambiente == "prod" && row.vigencia == "estable"
    ])
    error_message = "Stable NSG table IDs differ."
  }
  assert {
    condition     = length(module.subnet_security.nsg_ids) == 11
    error_message = "Every application subnet requires its reviewed NSG."
  }
}

run "subnet_migration_explicitly_selected" {
  command = plan
  variables {
    active_temporary_nsg_rules = ["NSG-prod-11", "NSG-prod-12", "NSG-prod-14"]
    migration_change_reference = "MOCK-CHANGE-ONLY"
  }
  assert {
    condition     = length(module.subnet_security.rule_ids) == 17
    error_message = "Expected 14 stable and three explicitly selected temporary NSG IDs."
  }
}
