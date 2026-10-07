terraform {
  required_version = ">= 1.7.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  # Remote state (an azurerm backend) is configured once the pipeline work in
  # issue #23 provisions the storage account. Until then this environment
  # uses local state and must not be applied outside a single operator's
  # machine.
}

provider "azurerm" {
  features {}
}
