variable "location" {
  description = "Approved Azure region for this application environment."
  type        = string
  default     = "eastus2"
}

variable "resource_group_name" {
  description = "Resource group owned by this root; import it first if it already exists."
  type        = string
  default     = "rg-fa-network-test"
}

variable "owner_team" {
  description = "Team responsible for the network resources."
  type        = string
  default     = "equipo-plataforma"
}
