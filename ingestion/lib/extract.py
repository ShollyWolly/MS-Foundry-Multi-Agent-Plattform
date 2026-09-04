"""Extracts clean structured content (narrative paragraphs + tables) from a PDF via Azure AI
Content Understanding's prebuilt-layout analyzer — chosen over classic Document Intelligence
because it merges a table spanning multiple PDF pages into one logical table object (confirmed
empirically: a 70-row inventory table spread across 4 PDF pages came back as a single
DocumentTable with row_count=74, not split per page).

Boilerplate (running page headers/footers, page numbers) is dropped here using Content
Understanding's own per-paragraph semantic role — far more precise than regex-guessing which
lines look like a repeated header.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .azure_clients import content_understanding_client

# SemanticRole values (Content Understanding is a string-enum SDK, so plain string comparison works).
BOILERPLATE_ROLES = {"pageHeader", "pageFooter", "pageNumber"}
HEADING_ROLES = {"title", "sectionHeading"}

_PAGE_FROM_SOURCE_RE = re.compile(r"^D\((\d+),")


def _page_from_source(source: str | None) -> int | None:
    """Content Understanding encodes the page number as the first value in the bounding-region
    `source` string, e.g. "D(1,0.69,3.43,...)" -> page 1."""
    if not source:
        return None
    m = _PAGE_FROM_SOURCE_RE.match(source)
    return int(m.group(1)) if m else None


def _span_within(span: dict, outer_span: dict) -> bool:
    return span["offset"] >= outer_span["offset"] and (span["offset"] + span["length"]) <= (
        outer_span["offset"] + outer_span["length"]
    )


@dataclass
class NarrativeParagraph:
    heading: str
    text: str
    page_number: int | None


@dataclass
class ExtractedTable:
    caption: str | None
    header_rows: list[list[str]]
    data_rows: list[list[str]]
    page_number: int | None


@dataclass
class ExtractedDocument:
    paragraphs: list[NarrativeParagraph]
    tables: list[ExtractedTable]


def extract_pdf(pdf_path: Path) -> ExtractedDocument:
    client = content_understanding_client()
    data = pdf_path.read_bytes()
    poller = client.begin_analyze_binary("prebuilt-layout", data, content_type="application/pdf")
    result = poller.result()
    content = result.contents[0]

    table_spans = [t.span for t in (content.tables or [])]

    paragraphs: list[NarrativeParagraph] = []
    current_heading = ""
    for p in content.paragraphs or []:
        if p.role in BOILERPLATE_ROLES:
            continue
        if p.role in HEADING_ROLES:
            current_heading = p.content
            continue
        # Paragraphs that fall inside a table's span are the table's own cell text, already
        # captured structurally in content.tables — skip here to avoid indexing it twice.
        if any(_span_within(p.span, ts) for ts in table_spans):
            continue
        if p.content and p.content.strip():
            paragraphs.append(NarrativeParagraph(current_heading, p.content.strip(), _page_from_source(p.source)))

    tables: list[ExtractedTable] = []
    for t in content.tables or []:
        grid: dict[tuple[int, int], str] = {}
        header_row_indices: set[int] = set()
        for cell in t.cells:
            grid[(cell.row_index, cell.column_index)] = cell.content or ""
            if cell.kind == "columnHeader":
                header_row_indices.add(cell.row_index)

        def row(r: int) -> list[str]:
            return [grid.get((r, c), "") for c in range(t.column_count)]

        # A table spanning multiple PDF pages repeats its header visually on every page, and
        # Content Understanding tags each repetition's row(s) as columnHeader too — with row
        # indices that keep incrementing across pages rather than resetting, and page-1 *data*
        # rows sitting between page-1's header block and page-2's repeated header block (e.g.
        # header rows [0, 1, 9, 10] with real data at both [2..8] and [11..28]). So data rows
        # must be "every row index not tagged as a header", not "everything after the last
        # header index" — the latter silently drops page-1's data. Header content is deduped by
        # value, keeping first-occurrence order, so a 2-row header repeated on 2 pages doesn't
        # render 4 times.
        # Small/simple tables sometimes get no cells tagged columnHeader at all (Content
        # Understanding heuristically decides this, and doesn't always tag it for a short
        # table) — in that case header_row_indices is empty, and row 0 must still be treated as
        # the implicit header for BOTH header_rows and the data-row exclusion set, or row 0 ends
        # up duplicated as its own first "data" row.
        effective_header_indices = header_row_indices or {0}
        raw_header_rows = [row(r) for r in sorted(effective_header_indices)]
        header_rows = list(map(list, dict.fromkeys(tuple(r) for r in raw_header_rows)))
        data_row_indices = [r for r in range(t.row_count) if r not in effective_header_indices]
        data_rows = [row(r) for r in data_row_indices]

        tables.append(
            ExtractedTable(
                caption=t.caption.content if getattr(t, "caption", None) else None,
                header_rows=header_rows,
                data_rows=data_rows,
                page_number=_page_from_source(t.source),
            )
        )

    return ExtractedDocument(paragraphs=paragraphs, tables=tables)


@dataclass
class NarrativeSection:
    heading: str
    text: str
    page_number: int | None


def group_into_sections(paragraphs: list[NarrativeParagraph]) -> list[NarrativeSection]:
    """Groups consecutive paragraphs sharing a heading into one section — the unit the ingestion
    pipeline writes as one sidecar blob, so SplitSkill's per-blob chunking can never cut across a
    section boundary (see preprocess.py)."""
    sections: list[NarrativeSection] = []
    current_heading: str | None = None
    buffer: list[NarrativeParagraph] = []

    def flush():
        if buffer:
            sections.append(NarrativeSection(
                heading=buffer[0].heading,
                text="\n\n".join(p.text for p in buffer),
                page_number=buffer[0].page_number,
            ))

    for p in paragraphs:
        if current_heading is not None and p.heading != current_heading:
            flush()
            buffer = []
        buffer.append(p)
        current_heading = p.heading
    flush()
    return sections
