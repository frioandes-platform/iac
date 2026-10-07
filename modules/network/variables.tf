variable "environment" {
  description = "Environment name as it appears in the env column of data/ip-plan.csv."
  type        = string

  validation {
    condition     = contains(["prod", "test", "dev"], var.environment)
    error_message = "environment must be prod, test or dev."
  }
}

variable "resource_group_name" {
  description = "Resource group where the virtual network and its subnets are created."
  type        = string
}

variable "location" {
  description = "Azure region for the virtual network."
  type        = string
  default     = "eastus2"
}

variable "tags" {
  description = "Tags applied to the virtual network and every subnet."
  type        = map(string)
  default     = {}
}
