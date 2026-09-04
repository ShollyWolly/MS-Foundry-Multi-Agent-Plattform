resource "azurerm_resource_group" "this" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

# The modern ("Foundry") pattern: a Cognitive Services account of kind AIServices with
# project management enabled, rather than the legacy azurerm_ai_foundry hub resource (which
# requires a storage account + key vault this pattern doesn't need).
resource "azurerm_cognitive_account" "foundry" {
  name                          = var.foundry_account_name
  resource_group_name           = azurerm_resource_group.this.name
  location                      = azurerm_resource_group.this.location
  kind                          = "AIServices"
  sku_name                      = "S0"
  custom_subdomain_name         = var.foundry_account_name
  project_management_enabled    = true
  public_network_access_enabled = true
  tags                          = var.tags

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_cognitive_account_project" "this" {
  name                 = var.foundry_project_name
  cognitive_account_id = azurerm_cognitive_account.foundry.id
  location             = azurerm_resource_group.this.location
  display_name         = var.foundry_project_name
  tags                 = var.tags

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_cognitive_deployment" "model" {
  name                 = var.model_deployment_name
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = var.model_name
    version = var.model_version
  }

  sku {
    name     = var.model_sku_name
    capacity = var.model_capacity
  }
}

# Minimum role Microsoft's docs list for creating/using agents via the SDK or REST API
# (agents/*/read, agents/*/action, agents/*/delete), scoped to the project.
resource "azurerm_role_assignment" "sp_ai_user" {
  scope                = azurerm_cognitive_account_project.this.id
  role_definition_name = "Foundry User"
  principal_id         = data.azuread_service_principal.this.object_id
}

data "azuread_service_principal" "this" {
  client_id = var.service_principal_client_id
}

# Stores per-user conversation *metadata* (id, title, owner, timestamps, Foundry conversation
# id) — not chat message content, which stays in Foundry's own Conversations API. Foundry's
# conversation store is agent-scoped, not user-scoped, so this is what makes "my conversations"
# (vs. everyone's) possible once there's more than one user. Serverless: no baseline cost, pure
# pay-per-request, appropriate for this dev-sandbox stage.
resource "azurerm_cosmosdb_account" "this" {
  name                = var.cosmosdb_account_name
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"
  tags                = var.tags

  consistency_policy {
    consistency_level = "Session"
  }

  capabilities {
    name = "EnableServerless"
  }

  geo_location {
    location          = azurerm_resource_group.this.location
    failover_priority = 0
  }
}

resource "azurerm_cosmosdb_sql_database" "this" {
  name                = var.cosmosdb_database_name
  resource_group_name = azurerm_resource_group.this.name
  account_name        = azurerm_cosmosdb_account.this.name
}

resource "azurerm_cosmosdb_sql_container" "conversations" {
  name                = var.cosmosdb_conversations_container_name
  resource_group_name = azurerm_resource_group.this.name
  account_name        = azurerm_cosmosdb_account.this.name
  database_name       = azurerm_cosmosdb_sql_database.this.name
  partition_key_paths = ["/userId"]
  # No `throughput` argument — serverless accounts are pay-per-request and reject a
  # provisioned-throughput value on the container.
}

# Cosmos DB's data-plane RBAC is separate from ARM roles (azurerm_role_assignment above grants
# ARM/control-plane access only) — this is what actually lets the SP read/write documents.
# "00000000-0000-0000-0000-000000000002" is Cosmos DB's fixed, built-in "Data Contributor" role ID.
resource "azurerm_cosmosdb_sql_role_assignment" "sp_data_contributor" {
  resource_group_name = azurerm_resource_group.this.name
  account_name        = azurerm_cosmosdb_account.this.name
  role_definition_id  = "${azurerm_cosmosdb_account.this.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = data.azuread_service_principal.this.object_id
  scope               = azurerm_cosmosdb_account.this.id
}
