#!/usr/bin/env python3
"""Idempotent bootstrap for the Search index + both indexer pipelines (narrative, table).
Analogous role to infra/scripts/create_agent.py: indexers/skillsets/data sources are Search
data-plane objects with no native azurerm Terraform resource, so a Python script using the SDK
fills that gap, same as Foundry Agents do.

Safe to re-run — every object is created via create_or_update. Run with the `rag-ingestion`
conda env active, after ingestion/preprocess.py has uploaded at least one PDF's blobs:

    conda activate rag-ingestion
    python ingestion/setup_indexer.py
    python ingestion/setup_indexer.py --run   # also triggers both indexers and waits for them
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from azure.search.documents.indexes.models import (  # noqa: E402
    AzureOpenAIEmbeddingSkill,
    FieldMapping,
    FieldMappingFunction,
    IndexProjectionMode,
    InputFieldMappingEntry,
    NativeBlobSoftDeleteDeletionDetectionPolicy,
    OutputFieldMappingEntry,
    SearchIndexerDataContainer,
    SearchIndexerDataSourceConnection,
    SearchIndexerIndexProjection,
    SearchIndexerIndexProjectionSelector,
    SearchIndexerIndexProjectionsParameters,
    SearchIndexerSkillset,
    SearchIndexer,
    SplitSkill,
)

from lib.azure_clients import (  # noqa: E402
    search_indexer_client,
    storage_account_managed_identity_connection_string,
    terraform_outputs,
)
from lib.config import load_config  # noqa: E402
from lib.retry import retry_with_backoff  # noqa: E402
from lib.search_index import ensure_index  # noqa: E402

NARRATIVE_DATA_SOURCE_NAME = "reports-sections-narrative-datasource"
TABLE_DATA_SOURCE_NAME = "reports-sections-table-datasource"
NARRATIVE_SKILLSET_NAME = "reports-narrative-skillset"
TABLE_SKILLSET_NAME = "reports-table-skillset"
NARRATIVE_INDEXER_NAME = "reports-narrative-indexer"
TABLE_INDEXER_NAME = "reports-table-indexer"

# Common metadata field mappings: blob custom metadata keys surface as top-level fields with the
# same name automatically, so these just carry them straight through into the matching index
# field (no mapping function needed — all are valid Search field identifiers already).
COMMON_FIELD_MAPPINGS = [
    FieldMapping(source_field_name="metadata_storage_path", target_field_name="source_blob_path"),
    FieldMapping(source_field_name="report_key", target_field_name="report_key"),
    FieldMapping(source_field_name="report_id", target_field_name="report_id"),
    FieldMapping(source_field_name="report_title", target_field_name="report_title"),
    FieldMapping(source_field_name="department", target_field_name="department"),
    FieldMapping(source_field_name="year", target_field_name="year"),
    FieldMapping(source_field_name="chunk_type", target_field_name="chunk_type"),
    FieldMapping(source_field_name="section_heading", target_field_name="section_heading"),
    FieldMapping(source_field_name="page_number", target_field_name="page_number"),
    FieldMapping(source_field_name="source_pdf_url", target_field_name="source_pdf_url"),
]


def ensure_data_sources() -> None:
    client = search_indexer_client()
    config = load_config()
    container_name = config["sections_container"]
    connection_string = storage_account_managed_identity_connection_string()
    # Same container, split by virtual-folder prefix ("sections/" vs "tables/") — this is what
    # keeps the narrative indexer (SplitSkill-based) from ever touching pre-chunked table blobs
    # and vice versa. A blob data source's container "query" is exactly this path-prefix filter.
    for name, prefix in [(NARRATIVE_DATA_SOURCE_NAME, "sections/"), (TABLE_DATA_SOURCE_NAME, "tables/")]:
        data_source = SearchIndexerDataSourceConnection(
            name=name,
            type="azureblob",
            connection_string=connection_string,
            container=SearchIndexerDataContainer(name=container_name, query=prefix),
            # Must be attached from the very first run: a blob deleted before this policy exists
            # becomes a permanent index orphan even after adding the policy later.
            data_deletion_detection_policy=NativeBlobSoftDeleteDeletionDetectionPolicy(),
        )
        client.create_or_update_data_source_connection(data_source)


def _embedding_skill(context: str, inputs_source: str) -> AzureOpenAIEmbeddingSkill:
    outputs = terraform_outputs()
    account = outputs["foundry_account_name"]
    deployment = outputs["embedding_deployment_name"]
    return AzureOpenAIEmbeddingSkill(
        name="embed",
        context=context,
        inputs=[InputFieldMappingEntry(name="text", source=inputs_source)],
        outputs=[OutputFieldMappingEntry(name="embedding", target_name="content_vector")],
        resource_url=f"https://{account}.openai.azure.com",
        deployment_name=deployment,
        model_name="text-embedding-3-small",
        dimensions=1536,
    )


def ensure_narrative_skillset(index_name: str, narrative_max_tokens: int, narrative_overlap_tokens: int) -> None:
    client = search_indexer_client()
    split_skill = SplitSkill(
        name="split",
        context="/document",
        text_split_mode="pages",
        maximum_page_length=narrative_max_tokens,
        page_overlap_length=narrative_overlap_tokens,
        inputs=[InputFieldMappingEntry(name="text", source="/document/content")],
        outputs=[OutputFieldMappingEntry(name="textItems", target_name="pages")],
    )
    embed_skill = _embedding_skill("/document/pages/*", "/document/pages/*")

    # Index projections use only their own `mappings` list — the indexer's top-level
    # field_mappings never reach documents created via projection. Metadata fields must be
    # re-declared here, sourced from the parent document root (/document/<field>), not just the
    # page-level content/vector.
    index_projection = SearchIndexerIndexProjection(
        selectors=[
            SearchIndexerIndexProjectionSelector(
                target_index_name=index_name,
                parent_key_field_name="parent_id",
                source_context="/document/pages/*",
                mappings=[
                    InputFieldMappingEntry(name="content", source="/document/pages/*"),
                    InputFieldMappingEntry(name="content_vector", source="/document/pages/*/content_vector"),
                    InputFieldMappingEntry(name="report_key", source="/document/report_key"),
                    InputFieldMappingEntry(name="report_id", source="/document/report_id"),
                    InputFieldMappingEntry(name="report_title", source="/document/report_title"),
                    InputFieldMappingEntry(name="department", source="/document/department"),
                    InputFieldMappingEntry(name="year", source="/document/year"),
                    InputFieldMappingEntry(name="chunk_type", source="/document/chunk_type"),
                    InputFieldMappingEntry(name="section_heading", source="/document/section_heading"),
                    InputFieldMappingEntry(name="page_number", source="/document/page_number"),
                    InputFieldMappingEntry(name="source_blob_path", source="/document/metadata_storage_path"),
                    InputFieldMappingEntry(name="source_pdf_url", source="/document/source_pdf_url"),
                ],
            )
        ],
        parameters=SearchIndexerIndexProjectionsParameters(
            projection_mode=IndexProjectionMode.SKIP_INDEXING_PARENT_DOCUMENTS
        ),
    )

    skillset = SearchIndexerSkillset(
        name=NARRATIVE_SKILLSET_NAME,
        skills=[split_skill, embed_skill],
        index_projection=index_projection,
    )
    client.create_or_update_skillset(skillset)


def ensure_table_skillset() -> None:
    client = search_indexer_client()
    embed_skill = _embedding_skill("/document", "/document/content")
    skillset = SearchIndexerSkillset(name=TABLE_SKILLSET_NAME, skills=[embed_skill])
    client.create_or_update_skillset(skillset)


def ensure_indexers(index_name: str) -> None:
    client = search_indexer_client()

    narrative_indexer = SearchIndexer(
        name=NARRATIVE_INDEXER_NAME,
        data_source_name=NARRATIVE_DATA_SOURCE_NAME,
        skillset_name=NARRATIVE_SKILLSET_NAME,
        target_index_name=index_name,
        field_mappings=COMMON_FIELD_MAPPINGS,
        # No output_field_mappings here — content/content_vector are populated via index
        # projections above, not a direct skill-output -> index-field mapping.
    )
    client.create_or_update_indexer(narrative_indexer)

    table_indexer = SearchIndexer(
        name=TABLE_INDEXER_NAME,
        data_source_name=TABLE_DATA_SOURCE_NAME,
        skillset_name=TABLE_SKILLSET_NAME,
        target_index_name=index_name,
        field_mappings=[
            *COMMON_FIELD_MAPPINGS,
            # No index projections for the table pipeline (1 blob = 1 document) — the key field
            # needs an explicit value, base64-encoded since the raw blob path isn't itself a
            # valid Search key (keys must be URL-safe strings).
            FieldMapping(
                source_field_name="metadata_storage_path",
                target_field_name="id",
                mapping_function=FieldMappingFunction(name="base64Encode"),
            ),
            FieldMapping(source_field_name="metadata_storage_path", target_field_name="parent_id"),
            FieldMapping(source_field_name="content", target_field_name="content"),
        ],
        output_field_mappings=[
            FieldMapping(source_field_name="/document/content_vector", target_field_name="content_vector"),
        ],
    )
    client.create_or_update_indexer(table_indexer)


def run_and_wait(indexer_name: str, timeout_s: int = 600) -> None:
    client = search_indexer_client()
    client.run_indexer(indexer_name)
    start = time.time()
    while time.time() - start < timeout_s:
        status = client.get_indexer_status(indexer_name)
        last = status.last_result
        if last and last.status in ("success", "transientFailure", "persistentFailure"):
            print(f"  {indexer_name}: {last.status} ({last.item_count} items, {len(last.errors or [])} errors)")
            for e in (last.errors or [])[:5]:
                print(f"    error: {e.error_message}")
            return
        time.sleep(10)
    print(f"  {indexer_name}: timed out waiting for a result after {timeout_s}s")


def main() -> int:
    config = load_config()
    index_name = config["index_name"]

    print("Ensuring index...")
    retry_with_backoff(lambda: ensure_index(index_name), label="ensure_index")

    print("Ensuring data sources...")
    retry_with_backoff(ensure_data_sources, label="ensure_data_sources")

    print("Ensuring skillsets...")
    retry_with_backoff(
        lambda: ensure_narrative_skillset(
            index_name, config["chunking"]["narrative_max_tokens"], config["chunking"]["narrative_overlap_tokens"]
        ),
        label="ensure_narrative_skillset",
    )
    retry_with_backoff(ensure_table_skillset, label="ensure_table_skillset")

    print("Ensuring indexers...")
    retry_with_backoff(lambda: ensure_indexers(index_name), label="ensure_indexers")

    if "--run" in sys.argv:
        print("\nRunning indexers...")
        run_and_wait(NARRATIVE_INDEXER_NAME)
        run_and_wait(TABLE_INDEXER_NAME)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
