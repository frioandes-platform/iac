variable "location" {
  type        = string
  default     = "eastus2"
  description = "Approved hub region."
}
variable "owner_team" {
  type        = string
  default     = "equipo-plataforma"
  description = "Network operations owner."
}
variable "protected_environments" {
  type        = set(string)
  default     = ["dev"]
  description = "Rules loaded into the one shared firewall; extend deliberately to test and prod."
}
variable "security_token_values" {
  type        = map(list(string))
  default     = {}
  description = "Approved replacements for unresolved design tokens; test fixture values are not production inputs."
}
variable "active_temporary_firewall_rules" {
  type        = set(string)
  default     = []
  description = "Explicit migration rule IDs currently approved."
}
variable "migration_change_reference" {
  type        = string
  default     = ""
  description = "Required change approval reference for temporary rules."
}
