"""Writes the raw, unformatted data behind a report to a JSON sidecar next to its PDF, so a
RAG answer can later be checked against the real numbers instead of just eyeballing the PDF.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def write_ground_truth(
    path: Path,
    tables: dict[str, pd.DataFrame],
    aggregates: dict | None = None,
    *,
    report_id: str,
    report_title: str,
    department: str,
    year: int,
) -> None:
    # report_id/report_title/department/year are the identity metadata the ingestion pipeline
    # reads to tag search index documents — the single source of truth for "which report is
    # this, whose data, what year", replacing a hand-maintained filename->department map.
    data = {
        "report_id": report_id,
        "report_title": report_title,
        "department": department,
        "year": year,
        "tables": {name: json.loads(df.to_json(orient="records")) for name, df in tables.items()},
        "aggregates": aggregates or {},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))


def write_origin_csv(df: pd.DataFrame, path: Path) -> None:
    """Writes the transaction/event-grain DataFrame a report's aggregated tables are computed
    FROM — the raw synthetic "data store load" table, including noise columns. Kept separate
    from write_ground_truth (JSON, aggregated, no noise columns): different consumers (RAG
    ground-truth checking vs. a future data-store load)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
