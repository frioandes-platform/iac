locals {
  environment = "prod"
  tags = {
    ambiente    = local.environment
    carga       = "red"
    costo       = local.environment == "prod" ? "compartido" : "pruebas"
    criticidad  = local.environment == "prod" ? "alta" : "baja"
    responsable = var.owner_team
  }
}

resource "azurerm_resource_group" "network" {
  name     = var.resource_group_name
  location = var.location
  tags     = local.tags
}

module "network" {
  source = "../../modules/network"

  environment         = local.environment
  resource_group_name = azurerm_resource_group.network.name
  location            = azurerm_resource_group.network.location
  tags                = local.tags
}
