"""Shared Azure client/credential setup for the ingestion pipeline — same
EnvironmentCredential + terraform-outputs pattern as dataGeneration/lib/llm.py, reimplemented
here rather than imported from dataGeneration since this is a deliberately separate, decoupled
part of the project.
"""
from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path

from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.identity import EnvironmentCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient, SearchIndexerClient
from azure.storage.blob import BlobServiceClient
from openai import AzureOpenAI

REPO_ROOT = Path(__file__).resolve().parents[2]
TERRAFORM_DIR = REPO_ROOT / "infra" / "terraform"


@lru_cache(maxsize=1)
def terraform_outputs() -> dict:
    result = subprocess.run(
        ["terraform", "output", "-json"], cwd=TERRAFORM_DIR, capture_output=True, text=True, check=True
    )
    return {k: v["value"] for k, v in json.loads(result.stdout).items()}


@lru_cache(maxsize=1)
def content_understanding_client() -> ContentUnderstandingClient:
    account = terraform_outputs()["foundry_account_name"]
    endpoint = f"https://{account}.cognitiveservices.azure.com/"
    return ContentUnderstandingClient(endpoint, EnvironmentCredential())


@lru_cache(maxsize=1)
def embedding_client_and_deployment() -> tuple[AzureOpenAI, str]:
    outputs = terraform_outputs()
    account = outputs["foundry_account_name"]
    deployment = outputs["embedding_deployment_name"]
    token_provider = get_bearer_token_provider(EnvironmentCredential(), "https://cognitiveservices.azure.com/.default")
    client = AzureOpenAI(
        azure_endpoint=f"https://{account}.openai.azure.com/",
        azure_ad_token_provider=token_provider,
        api_version="2024-10-21",
    )
    return client, deployment


@lru_cache(maxsize=1)
def search_index_client() -> SearchIndexClient:
    endpoint = terraform_outputs()["search_service_endpoint"]
    return SearchIndexClient(endpoint, EnvironmentCredential())


def get_search_client(index_name: str) -> SearchClient:
    endpoint = terraform_outputs()["search_service_endpoint"]
    return SearchClient(endpoint, index_name, EnvironmentCredential())


@lru_cache(maxsize=1)
def search_indexer_client() -> SearchIndexerClient:
    endpoint = terraform_outputs()["search_service_endpoint"]
    return SearchIndexerClient(endpoint, EnvironmentCredential())


@lru_cache(maxsize=1)
def blob_service_client() -> BlobServiceClient:
    account = terraform_outputs()["reports_storage_account_name"]
    return BlobServiceClient(f"https://{account}.blob.core.windows.net", EnvironmentCredential())


def storage_account_managed_identity_connection_string() -> str:
    """Builds the ResourceId= form of a storage connection string Azure AI Search's blob data
    source needs to authenticate via managed identity instead of an account key."""
    outputs = terraform_outputs()
    return (
        f"ResourceId=/subscriptions/{outputs['subscription_id']}"
        f"/resourceGroups/{outputs['resource_group_name']}"
        f"/providers/Microsoft.Storage/storageAccounts/{outputs['reports_storage_account_name']};"
    )
