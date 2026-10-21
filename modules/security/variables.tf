variable "name" {
  description = "Name of the single shared hub firewall."
  type        = string
  default     = "afw-fa-hub"
}

variable "resource_group_name" {
  description = "Connectivity resource group owned by the root module."
  type        = string
}

variable "location" {
  description = "Approved Azure region."
  type        = string
}

variable "firewall_subnet_id" {
  description = "ID of AzureFirewallSubnet from the approved hub address plan."
  type        = string
}

variable "management_subnet_id" {
  description = "ID of AzureFirewallManagementSubnet; created before the firewall."
  type        = string
}

variable "tags" {
  description = "Governance tags for all taggable security resources."
  type        = map(string)
}

variable "environments" {
  description = "Environment rules loaded into the ONE shared policy, not separate firewalls."
  type        = set(string)
  default     = ["dev"]
  validation {
    condition     = length(var.environments) > 0 && alltrue([for env in var.environments : contains(["dev", "test", "prod"], env)])
    error_message = "Select at least one of dev, test, prod."
  }
}

variable "token_values" {
  description = "Explicit replacements for whole placeholder tokens in the source CSV. No defaults invent production endpoints."
  type        = map(list(string))
  default     = {}
  validation {
    condition = (
      alltrue([for key in keys(var.token_values) : strcontains(key, "<") && strcontains(key, ">")]) &&
      alltrue([for values in values(var.token_values) : length(values) > 0 && alltrue([for value in values : trimspace(value) != "" && !contains(["*", "0.0.0.0/0", "::/0"], value) && !strcontains(value, "<") && !strcontains(value, ">")])])
    )
    error_message = "Replacement lists must be nonempty, resolved, and cannot introduce an unrestricted wildcard."
  }
}

variable "active_temporary_rule_ids" {
  description = "Explicit temporary rule IDs still needed during migration; remove each at its own retirement milestone."
  type        = set(string)
  default     = []
}

variable "migration_change_reference" {
  description = "Approved change/ticket for enabling temporary rules. Required when any are active."
  type        = string
  default     = ""
}
