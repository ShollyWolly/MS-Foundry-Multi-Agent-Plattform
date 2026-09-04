"""Table chunking — the one piece of chunking that stays permanently in Python rather than
moving to Azure AI Search's built-in SplitSkill, because SplitSkill has no concept of "repeat
these header rows in every split." Each chunk is one row-group with the header row(s) repeated,
so a chunk pulled out of context by a retriever is still legible on its own (e.g. "APAC | Q3 |
$1,410k" means nothing without the column headers next to it). Narrative chunking now happens
inside the indexer's skillset (SplitSkill, per-section blob) — see preprocess.py/setup_indexer.py.
"""
from __future__ import annotations

from dataclasses import dataclass

import tiktoken

from .extract import ExtractedTable

_ENCODING = tiktoken.get_encoding("cl100k_base")


def _token_len(text: str) -> int:
    return len(_ENCODING.encode(text))


@dataclass
class TableChunk:
    content: str
    caption: str
    page_number: int | None


def _rows_to_markdown(header_rows: list[list[str]], data_rows: list[list[str]]) -> str:
    lines = []
    for row in header_rows:
        lines.append("| " + " | ".join(row) + " |")
    lines.append("| " + " | ".join("---" for _ in header_rows[0]) + " |")
    for row in data_rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def chunk_table(table: ExtractedTable, max_tokens: int) -> list[TableChunk]:
    header_tokens = _token_len(_rows_to_markdown(table.header_rows, []))
    chunks: list[TableChunk] = []
    row_group: list[list[str]] = []
    group_tokens = header_tokens

    def flush():
        if not row_group:
            return
        body = _rows_to_markdown(table.header_rows, row_group)
        text = f"{table.caption}\n\n{body}" if table.caption else body
        chunks.append(TableChunk(text, table.caption or "", table.page_number))

    for row in table.data_rows:
        row_tokens = _token_len("| " + " | ".join(row) + " |")
        if row_group and group_tokens + row_tokens > max_tokens:
            flush()
            row_group, group_tokens = [], header_tokens
        row_group.append(row)
        group_tokens += row_tokens
    flush()
    return chunks
