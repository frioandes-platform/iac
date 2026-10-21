variable "location" {
  description = "Approved Azure region for this application environment."
  type        = string
  default     = "eastus2"
}

variable "resource_group_name" {
  description = "Resource group owned by this root; import it first if it already exists."
  type        = string
  default     = "rg-fa-network-prod"
}

variable "owner_team" {
  description = "Team responsible for the network resources."
  type        = string
  default     = "equipo-plataforma"
}

variable "security_token_values" {
  type        = map(list(string))
  default     = {}
  description = "Approved source-IP token replacements; no guessed production values."
}
variable "active_temporary_nsg_rules" {
  type        = set(string)
  default     = []
  description = "Explicit temporary NSG IDs still needed during migration."
}
variable "migration_change_reference" {
  type        = string
  default     = ""
  description = "Approval reference for temporary NSG rules."
}
