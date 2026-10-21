mock_provider "azurerm" {}
variables {
  security_token_values = jsondecode(file("../../tests/fixtures/security-tokens.json"))
}
run "subnet_policy_matches_table" {
  command = plan
  assert {
    condition = toset(module.subnet_security.rule_ids) == toset([
      for row in csvdecode(file("../../modules/security/data/firewall-policy.csv")) : row.id
      if row.punto_control == "nsg" && row.ambiente == "dev" && row.vigencia == "estable"
    ])
    error_message = "Stable NSG table IDs differ."
  }
  assert {
    condition     = length(module.subnet_security.nsg_ids) == 11
    error_message = "Every application subnet requires its reviewed NSG."
  }
}
