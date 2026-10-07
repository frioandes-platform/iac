locals {
  environment = "prod"
}

resource "azurerm_resource_group" "network" {
  name     = "rg-fa-network-${local.environment}"
  location = var.location

  tags = {
    ambiente    = local.environment
    carga       = "red"
    costo       = "compartido"
    criticidad  = "alta"
    responsable = "equipo-plataforma"
  }
}

module "network" {
  source = "../../modules/network"

  environment         = local.environment
  resource_group_name = azurerm_resource_group.network.name
  location            = var.location
  tags                = azurerm_resource_group.network.tags
}
