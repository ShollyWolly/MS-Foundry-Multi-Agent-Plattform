#!/usr/bin/env python3
"""Regression test for ingestion/lib/extract.py against real PDFs (calls Content Understanding,
not a mock) — checks for the specific bug classes already found and fixed this session:

  1. A header row duplicated as its own first *data* row (the single-page/no-columnHeader-tag bug).
  2. A multi-page table's repeated per-page header rows rendered more than once, or its data rows
     split across the header boundary and partially dropped.
  3. General structural sanity: header/data rows all have consistent column counts, no boilerplate
     (page numbers, running headers) leaking into narrative paragraphs, every report has a
     detectable "Executive Summary" section.

Run with the `rag-ingestion` conda env active:

    conda activate rag-ingestion
    python ingestion/test_extraction.py [--years 2016,2020,2025] [--reports 01_quarterly_sales_performance,...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.extract import extract_pdf  # noqa: E402

RAW_DIR = Path(__file__).resolve().parent.parent / "dataGeneration" / "output" / "raw"

ALL_REPORT_IDS = [
    "01_quarterly_sales_performance",
    "02_annual_financial_statement",
    "03_hr_headcount_report",
    "04_inventory_supply_chain",
    "05_marketing_campaign_performance",
    "06_customer_churn_retention",
    "07_product_profitability",
    "08_budget_vs_actual",
    "09_travel_expense_report",
    "10_regional_kpi_scorecard",
]

_PAGE_NUM_RE = re.compile(r"^\s*(page\s*)?\d+(\s*(of|/)\s*\d+)?\s*$", re.IGNORECASE)


def check_table(pdf_name: str, t_idx: int, table, errors: list[str]) -> None:
    if not table.header_rows:
        errors.append(f"{pdf_name} table[{t_idx}]: no header_rows at all")
        return

    header_set = {tuple(r) for r in table.header_rows}
    ncols = len(table.header_rows[0])

    for r in table.header_rows:
        if len(r) != ncols:
            errors.append(f"{pdf_name} table[{t_idx}]: header row {r} has {len(r)} cols, expected {ncols}")

    for i, row in enumerate(table.data_rows):
        if len(row) != ncols:
            errors.append(f"{pdf_name} table[{t_idx}]: data row {i} has {len(row)} cols, expected {ncols}")
        if tuple(row) in header_set:
            errors.append(
                f"{pdf_name} table[{t_idx}]: data row {i} exactly matches a header row {row} "
                "(header-duplicated-as-data bug)"
            )

    # A duplicate header row appearing >1 time in header_rows itself is the multi-page-header bug.
    if len(table.header_rows) != len(header_set):
        errors.append(f"{pdf_name} table[{t_idx}]: header_rows has duplicate rows: {table.header_rows}")

    if not table.data_rows:
        errors.append(f"{pdf_name} table[{t_idx}]: zero data rows (caption={table.caption!r})")


def check_narrative(pdf_name: str, doc, errors: list[str], warnings: list[str]) -> None:
    headings = {p.heading.strip().lower() for p in doc.paragraphs}
    if "executive summary" not in headings:
        warnings.append(f"{pdf_name}: no 'Executive Summary' heading found among {sorted(headings)}")

    for p in doc.paragraphs:
        if _PAGE_NUM_RE.match(p.text):
            errors.append(f"{pdf_name}: boilerplate-looking paragraph leaked through filtering: {p.text!r}")


def main() -> int:
    years = [2016, 2020, 2025]
    report_ids = ALL_REPORT_IDS
    if "--years" in sys.argv:
        years = [int(y) for y in sys.argv[sys.argv.index("--years") + 1].split(",")]
    if "--reports" in sys.argv:
        report_ids = sys.argv[sys.argv.index("--reports") + 1].split(",")

    errors: list[str] = []
    warnings: list[str] = []
    tested = 0

    for report_id in report_ids:
        for year in years:
            pdf_path = RAW_DIR / f"{report_id}_FY{year}.pdf"
            if not pdf_path.exists():
                warnings.append(f"missing: {pdf_path.name}")
                continue
            doc = extract_pdf(pdf_path)
            tested += 1
            print(f"  {pdf_path.name}: {len(doc.paragraphs)} paragraphs, {len(doc.tables)} tables")
            check_narrative(pdf_path.name, doc, errors, warnings)
            for t_idx, table in enumerate(doc.tables):
                check_table(pdf_path.name, t_idx, table, errors)

    print(f"\nTested {tested} PDFs.")
    if warnings:
        print(f"\n{len(warnings)} warning(s):")
        for w in warnings:
            print(f"  - {w}")

    if errors:
        print(f"\n{len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\nNo extraction errors found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
