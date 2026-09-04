"""Additional cleanup beyond extract.py's role-based boilerplate removal: drops trivially short
/ near-empty fragments that survive extraction (e.g. a stray single word or punctuation-only
paragraph) so they don't become useless, low-signal chunks. Most of the real "filtering" work
(running headers/footers, page numbers) is already done in extract.py using Content
Understanding's own semantic-role metadata, which is far more reliable than the regex/heuristic
boilerplate-stripping this module would otherwise need to do.
"""
from __future__ import annotations

from .extract import ExtractedDocument, ExtractedTable, NarrativeParagraph

MIN_PARAGRAPH_WORDS = 3


def filter_document(doc: ExtractedDocument) -> ExtractedDocument:
    paragraphs = [
        p for p in doc.paragraphs if len(p.text.split()) >= MIN_PARAGRAPH_WORDS
    ]
    tables = [t for t in doc.tables if t.data_rows]  # drop tables that ended up with no data rows
    return ExtractedDocument(paragraphs=paragraphs, tables=tables)


__all__ = ["filter_document", "ExtractedDocument", "ExtractedTable", "NarrativeParagraph"]
