# Configured by #23 with OIDC and a separate state key for this root.
# Local mocked checks continue to use terraform init -backend=false.
terraform {
  backend "azurerm" {}
}
