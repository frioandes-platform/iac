locals {
  environment = "test"
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

module "subnet_security" {
  source                     = "../../modules/security/subnet-controls"
  environment                = local.environment
  resource_group_name        = azurerm_resource_group.network.name
  location                   = var.location
  tags                       = local.tags
  subnet_ids                 = module.network.subnet_ids
  token_values               = var.security_token_values
  active_temporary_rule_ids  = var.active_temporary_nsg_rules
  migration_change_reference = var.migration_change_reference
}
