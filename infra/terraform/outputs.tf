output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "subscription_id" {
  description = "Used by ingestion/lib/azure_clients.py to build the managed-identity form of the storage connection string for the Search indexer's blob data source."
  value       = var.subscription_id
}

output "foundry_account_name" {
  value = azurerm_cognitive_account.foundry.name
}

output "foundry_project_endpoint" {
  description = "Data-plane endpoint for the Foundry project. Used by the agent bootstrap script and the webapp's AI_AGENT_ENDPOINT."
  value       = "https://${azurerm_cognitive_account.foundry.custom_subdomain_name}.services.ai.azure.com/api/projects/${azurerm_cognitive_account_project.this.name}"
}

output "model_deployment_name" {
  value = azurerm_cognitive_deployment.model.name
}

output "cosmosdb_endpoint" {
  value = azurerm_cosmosdb_account.this.endpoint
}

output "cosmosdb_database_name" {
  value = azurerm_cosmosdb_sql_database.this.name
}

output "cosmosdb_conversations_container_name" {
  value = azurerm_cosmosdb_sql_container.conversations.name
}

output "embedding_deployment_name" {
  value = azurerm_cognitive_deployment.embedding.name
}

output "search_service_name" {
  value = azurerm_search_service.this.name
}

output "search_service_endpoint" {
  value = azurerm_search_service.this.endpoint
}

output "reports_storage_account_name" {
  value = azurerm_storage_account.reports.name
}
