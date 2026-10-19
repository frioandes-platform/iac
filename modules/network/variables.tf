variable "environment" {
  description = "Application environment to select from the approved CSV snapshot."
  type        = string

  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "The environment must be dev, test, or prod; hub and reservations are out of scope."
  }
}

variable "resource_group_name" {
  description = "Name of the resource group managed by the environment root."
  type        = string
}

variable "location" {
  description = "Azure region selected by the environment root."
  type        = string
}

variable "tags" {
  description = "Governance tags for the VNet. Azure subnets do not support tags."
  type        = map(string)
}
