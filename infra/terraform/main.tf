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

# Lets the SP call the model deployment directly (plain chat completions,
# https://<account>.openai.azure.com/openai/deployments/<deployment>/chat/completions) — used by
# data/lib/llm.py to generate report narrative text. Separate from the "Foundry User" role above,
# which only covers the agents API, not raw OpenAI-compatible deployment calls.
resource "azurerm_role_assignment" "sp_openai_user" {
  scope                = azurerm_cognitive_account.foundry.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = data.azuread_service_principal.this.object_id
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

# Embedding model for the ingestion pipeline (ingestion/) — same account as the chat deployment,
# called the same way (plain OpenAI-compatible endpoint, not the agents API).
resource "azurerm_cognitive_deployment" "embedding" {
  name                 = var.embedding_deployment_name
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = var.embedding_model_name
    version = var.embedding_model_version
  }

  sku {
    name     = var.embedding_model_sku_name
    capacity = var.embedding_capacity
  }
}

# Lets the SP call Azure AI Content Understanding (ingestion/lib/extract.py) on this same
# account — a different data-action namespace than "Cognitive Services OpenAI User" above, which
# only covers OpenAI-namespace actions (chat/embeddings), not Content Understanding's.
resource "azurerm_role_assignment" "sp_cognitive_services_user" {
  scope                = azurerm_cognitive_account.foundry.id
  role_definition_name = "Cognitive Services User"
  principal_id         = data.azuread_service_principal.this.object_id
}

# Indexes the parsed/chunked/embedded report content (ingestion/) for RAG retrieval. Free SKU:
# $0/month, 50MB/3 indexes — comfortably enough for the ~10 small documents this project indexes.
#
# local_authentication_enabled=true + authentication_failure_mode set is NOT "leave local auth
# alone, also set a failure mode" despite the argument name — per the azurerm provider source
# (search_service_resource.go), this exact combination is the only way to land on ARM's
# `authOptions.aadOrApiKey` (both API-key and AAD/RBAC tokens accepted). The provider's other two
# states are `local_authentication_enabled=true` + no failure mode -> `apiKeyOnly` (the actual
# default — AAD tokens rejected outright regardless of any RBAC role assignment, which is what
# silently broke ingestion/lib/search_index.py's ensure_index() the first time, looking exactly
# like RBAC-propagation lag but was a config bug instead) and `local_authentication_enabled=false`
# -> `authOptions` omitted entirely ("RBAC Only Mode", no API keys at all).
resource "azurerm_search_service" "this" {
  name                         = var.search_service_name
  resource_group_name          = azurerm_resource_group.this.name
  location                     = azurerm_resource_group.this.location
  sku                          = var.search_service_sku
  local_authentication_enabled = true
  authentication_failure_mode  = "http401WithBearerChallenge"
  tags                         = var.tags

  # Lets the indexer read blobs from azurerm_storage_account.reports via AAD (managed identity),
  # no connection string/account key — consistent with this project's AAD-everywhere convention.
  identity {
    type = "SystemAssigned"
  }
}

# Azure AI Search's RBAC uses regular ARM role assignments (unlike Cosmos's separate data-plane
# RBAC system) — these are what let the SP manage the index schema and upload/query documents,
# via AAD auth (TokenCredential) rather than an admin API key.
resource "azurerm_role_assignment" "sp_search_service_contributor" {
  scope                = azurerm_search_service.this.id
  role_definition_name = "Search Service Contributor"
  principal_id         = data.azuread_service_principal.this.object_id
}

resource "azurerm_role_assignment" "sp_search_index_data_contributor" {
  scope                = azurerm_search_service.this.id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = data.azuread_service_principal.this.object_id
}

# ADLS Gen2 storage backing the indexer/skillset RAG pipeline (ingestion/). Two containers:
# reports-raw (source PDFs, referenced from the index for citation links) and reports-sections
# (the pre-processed sidecar text blobs the indexer's data source actually scans — kept in a
# separate container so the data source config can't accidentally target the wrong blob type).
# is_hns_enabled=true (ADLS Gen2) can't be changed after creation, so it's set now even though
# nothing here strictly requires the hierarchical namespace yet. Standard/LRS: cheapest
# redundancy tier, appropriate for a dev/demo project holding a handful of MB of documents.
resource "azurerm_storage_account" "reports" {
  name                     = var.reports_storage_account_name
  resource_group_name      = azurerm_resource_group.this.name
  location                 = azurerm_resource_group.this.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  is_hns_enabled           = true
  min_tls_version          = "TLS1_2"
  tags                     = var.tags

  # Required for the indexer's NativeBlobSoftDeleteDeletionDetectionPolicy — a deleted blob
  # becomes a soft-deleted tombstone the indexer can see (and act on) instead of vanishing
  # outright, which is what makes "delete a source blob -> its index documents get removed on
  # the next indexer run" actually work.
  blob_properties {
    delete_retention_policy {
      days = var.blob_soft_delete_retention_days
    }
  }
}

resource "azurerm_storage_container" "reports_raw" {
  name                  = "reports-raw"
  storage_account_id    = azurerm_storage_account.reports.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "reports_sections" {
  name                  = "reports-sections"
  storage_account_id    = azurerm_storage_account.reports.id
  container_access_type = "private"
}

# The search service's managed identity needs to read blobs to run the indexer.
resource "azurerm_role_assignment" "search_storage_blob_data_reader" {
  scope                = azurerm_storage_account.reports.id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = azurerm_search_service.this.identity[0].principal_id
}

# The deployment SP needs to upload PDFs + sidecar blobs from ingestion/preprocess.py.
resource "azurerm_role_assignment" "sp_storage_blob_data_contributor" {
  scope                = azurerm_storage_account.reports.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azuread_service_principal.this.object_id
}

# The search service's managed identity needs to call the embedding deployment via AAD too — the
# AzureOpenAIEmbeddingSkill inside the skillset authenticates as the indexer's own identity, not
# the deployment SP's. Same role already granted to the SP above, now also to the search service.
resource "azurerm_role_assignment" "search_openai_user" {
  scope                = azurerm_cognitive_account.foundry.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_search_service.this.identity[0].principal_id
}
