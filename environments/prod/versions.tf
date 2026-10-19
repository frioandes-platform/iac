terraform {
  required_version = ">= 1.7.0, < 2.0.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "= 4.62.0"
    }
  }
}

provider "azurerm" {
  features {}
  # Register required Azure namespaces through the platform bootstrap process.
  resource_provider_registrations = "none"
}
