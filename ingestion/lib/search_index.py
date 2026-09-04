"""Creates/updates the Azure AI Search index schema. One flat index across all reports,
departments, years and chunk types — Search has no cross-index joins, so sharding by any of
those dimensions would only make multi-department/multi-year queries worse; rich
filterable/facetable metadata fields on a single index is the standard pattern for this shape.

Populated by the indexer/skillset pipeline (see setup_indexer.py), not by direct document
upload — there is deliberately no upload_chunks()-equivalent here anymore.
"""
from __future__ import annotations

from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

from .azure_clients import search_index_client

EMBEDDING_DIMENSIONS = 1536
SEMANTIC_CONFIG_NAME = "default"
VECTOR_PROFILE_NAME = "default-vector-profile"


def ensure_index(index_name: str) -> None:
    client = search_index_client()

    fields = [
        # Index projections require the key field to have the "keyword" analyzer explicitly set.
        SearchField(
            name="id", type=SearchFieldDataType.String, key=True, searchable=True, analyzer_name="keyword"
        ),
        # Groups chunks from the same section/table sidecar blob (index-projection parent key).
        SimpleField(name="parent_id", type=SearchFieldDataType.String, filterable=True),
        # Groups all chunks belonging to one report+year instance, e.g. "quarterly_sales_performance:2025".
        SimpleField(name="report_key", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="report_id", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchableField(name="report_title", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="department", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="year", type=SearchFieldDataType.Int32, filterable=True, facetable=True, sortable=True),
        # "narrative" | "summary" | "table" — summary is the Executive-Summary-heading section,
        # split out from narrative since it answers "what happened" questions most directly.
        SimpleField(name="chunk_type", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchableField(name="section_heading", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="page_number", type=SearchFieldDataType.Int32, filterable=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=EMBEDDING_DIMENSIONS,
            vector_search_profile_name=VECTOR_PROFILE_NAME,
        ),
        SimpleField(name="source_blob_path", type=SearchFieldDataType.String),
        SimpleField(name="source_pdf_url", type=SearchFieldDataType.String),
    ]

    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="default-hnsw")],
        profiles=[VectorSearchProfile(name=VECTOR_PROFILE_NAME, algorithm_configuration_name="default-hnsw")],
    )

    # Left defined even though unusable on Free-tier Search (confirmed empirically — see
    # CLAUDE.md) — costs nothing to declare and is ready the moment the SKU is ever upgraded.
    semantic_search = SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name=SEMANTIC_CONFIG_NAME,
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="section_heading"),
                    content_fields=[SemanticField(field_name="content")],
                ),
            )
        ]
    )

    index = SearchIndex(
        name=index_name, fields=fields, vector_search=vector_search, semantic_search=semantic_search
    )
    client.create_or_update_index(index)
