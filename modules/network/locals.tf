# data/ip-plan.csv is a copy of docs/architecture/red/data/ip-plan.csv from
# frioandes-platform/planning (issue #8), the single source of the address
# ranges. Do not hardcode a CIDR in this module: read the CSV instead, and if
# it changes, copy it here again and update the hash noted in README.md.
locals {
  ip_plan = csvdecode(file("${path.module}/data/ip-plan.csv"))

  # Rows for this environment only. The hub and reserva rows belong to the
  # shared network module, not to an application environment.
  env_rows = [for row in local.ip_plan : row if row.env == var.environment]

  vnet_name = local.env_rows[0].vnet
  vnet_cidr = local.env_rows[0].vnet_cidr

  subnets = { for row in local.env_rows : row.subnet => row }

  # Delegations required by Azure for specific subnet services, from
  # docs/architecture/red/data/azure-subnet-constraints.csv in the planning repo.
  delegations = {
    "container-apps-workload-profiles" = {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
    "mysql-flexible" = {
      name    = "Microsoft.DBforMySQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
    "fabric-vnet-gateway" = {
      name    = "Microsoft.PowerPlatform/vnetaccesslinks"
      actions = ["Microsoft.Network/virtualNetworks/subnets/action"]
    }
    "functions-flex" = {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }

  # Subnets dedicated to private endpoints need endpoint network policies
  # disabled; every other subnet keeps the default.
  private_endpoint_services = ["private-endpoints"]
}
