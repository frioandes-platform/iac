variable "environment" {
  description = "Environment already instantiated by modules/network and subnet-controls."
  type        = string
  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "Use an approved application environment."
  }
}

variable "namespace_name" {
  description = "Globally unique Event Hubs namespace name; availability is checked by Azure."
  type        = string
  validation {
    condition     = can(regex("^[a-zA-Z][a-zA-Z0-9-]{4,48}[a-zA-Z0-9]$", var.namespace_name))
    error_message = "Use 6-50 letters, digits or hyphens, starting with a letter and ending with a letter or digit."
  }
}

variable "resource_group_name" {
  description = "Resource group in the application subscription."
  type        = string
}

variable "location" {
  description = "Region inherited from the application root, East US 2 for the reference environment."
  type        = string
}

variable "tags" {
  description = "Governance tags inherited from the root."
  type        = map(string)
}

variable "network" {
  description = "Network module outputs for the approved data private-endpoint subnet."
  type = object({
    vnet_id                           = string
    subnet_id                         = string
    private_endpoint_network_policies = string
  })
}

variable "security" {
  description = "Subnet-controls outputs; the caller must also depend on completed NSG associations."
  type = object({
    nsg_id   = string
    rule_ids = set(string)
  })
}

variable "private_dns_zone_id" {
  description = "Shared privatelink.servicebus.windows.net zone ID from the connectivity root; link it to the application VNet before enabling this module."
  type        = string
  validation {
    condition     = can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.Network/privateDnsZones/privatelink\\.servicebus\\.windows\\.net$", var.private_dns_zone_id))
    error_message = "Supply the shared Event Hubs private DNS zone resource ID."
  }
}

variable "sender_principal_ids" {
  description = "Stable labels to Entra object IDs (not client IDs). Use a Stream Analytics managed identity or an approved dev simulator."
  type        = map(string)
  default     = {}
  validation {
    condition     = alltrue([for id in values(var.sender_principal_ids) : can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", id))])
    error_message = "Sender principal IDs must be Entra object UUIDs."
  }
}

variable "receiver_principal_ids" {
  description = "Stable labels to Entra object IDs for the notifier or an approved dev consumer."
  type        = map(string)
  default     = {}
  validation {
    condition     = alltrue([for id in values(var.receiver_principal_ids) : can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", id))])
    error_message = "Receiver principal IDs must be Entra object UUIDs."
  }
}
