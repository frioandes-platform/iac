# A mocked plan exercises the real module without Azure authentication or resources.
mock_provider "azurerm" {}

run "approved_environment_network" {
  command = plan

  assert {
    condition     = module.network.vnet_name == "vnet-prod"
    error_message = "The root selected the wrong environment."
  }

  assert {
    condition = toset(module.network.address_space) == toset(distinct([
      for row in csvdecode(file("${path.root}/../../modules/network/data/ip-plan.csv")) : row.vnet_cidr
      if row.env == "prod"
    ]))
    error_message = "The planned VNet differs from the approved CSV."
  }

  assert {
    condition = jsonencode(module.network.subnet_prefixes) == jsonencode({
      for row in csvdecode(file("${path.root}/../../modules/network/data/ip-plan.csv")) : row.subnet => [row.cidr]
      if row.env == "prod"
    })
    error_message = "The planned subnet set or CIDRs differ from the approved CSV."
  }

  assert {
    condition     = length(module.network.subnet_prefixes) == 11
    error_message = "Review the expected topology when updating the approved snapshot."
  }

  assert {
    condition = (
      contains(module.network.subnet_delegations["snet-data"], "Microsoft.DBforMySQL/flexibleServers") &&
      contains(module.network.subnet_delegations["snet-app-torre"], "Microsoft.App/environments") &&
      contains(module.network.subnet_delegations["snet-app-portal"], "Microsoft.App/environments") &&
      contains(module.network.subnet_delegations["snet-telemetry-func"], "Microsoft.App/environments") &&
      contains(module.network.subnet_delegations["snet-fabric-egress"], "Microsoft.PowerPlatform/vnetaccesslinks") &&
      length(module.network.subnet_delegations["snet-ingest"]) == 0
    )
    error_message = "A service delegation is missing or private endpoints were delegated."
  }

  assert {
    condition     = module.network.private_endpoint_network_policies["snet-archive"] == "NetworkSecurityGroupEnabled"
    error_message = "Archive private endpoints must retain NSG-only policy enforcement."
  }
}
