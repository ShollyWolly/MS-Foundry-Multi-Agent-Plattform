variable "subscription_id" {
  description = "Azure subscription ID to deploy into."
  type        = string
}

variable "resource_group_name" {
  description = "Name of the resource group holding the Foundry stack."
  type        = string
  default     = "rg-multi-agent-platform"
}

variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "swedencentral"
}

variable "foundry_account_name" {
  description = "Name of the AI Foundry account (Cognitive Services AIServices account). Must be globally unique — used as the custom subdomain."
  type        = string
  default     = "foundry-multi-agent-platform"
}

variable "foundry_project_name" {
  description = "Name of the AI Foundry project within the account."
  type        = string
  default     = "multi-agent-platform"
}

variable "model_deployment_name" {
  description = "Deployment name for the model (also used as the model's deployment name the agent references)."
  type        = string
  default     = "gpt-5-mini"
}

variable "model_name" {
  description = "Underlying model name to deploy."
  type        = string
  default     = "gpt-5-mini"
}

variable "model_version" {
  description = "Model version to deploy. Pinned to the version Azure assigned by default on first deploy, to avoid perpetual plan drift."
  type        = string
  default     = "2025-08-07"
}

variable "model_sku_name" {
  description = "SKU name for the model deployment (deployment type). GlobalStandard quota for gpt-5-mini was exhausted subscription-wide at plan time, so this defaults to DataZoneStandard."
  type        = string
  default     = "DataZoneStandard"
}

variable "model_capacity" {
  description = "Capacity (in thousands of tokens per minute, per Azure's deployment SKU units) for the model deployment."
  type        = number
  default     = 10
}

variable "cosmosdb_account_name" {
  description = "Name of the Cosmos DB account used for per-user conversation metadata (not chat message content, which stays in Foundry). Must be globally unique."
  type        = string
  default     = "cosmos-multi-agent-platform"
}

variable "cosmosdb_database_name" {
  description = "Name of the Cosmos DB SQL database."
  type        = string
  default     = "multi-agent-platform"
}

variable "cosmosdb_conversations_container_name" {
  description = "Name of the Cosmos DB container storing conversation metadata, partitioned by /userId."
  type        = string
  default     = "conversations"
}

variable "service_principal_client_id" {
  description = "App (client) ID of the service principal that Terraform runs as and that the local webapp uses to call Foundry. Granted the Azure AI User role on the project."
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources."
  type        = map(string)
  default = {
    project = "multi-agent-platform"
  }
}
