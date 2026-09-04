#!/usr/bin/env python3
"""Independently re-derives each report's aggregated golden-JSON numbers from its origin CSV and
diffs them — confirms "the origin data aggregates back to the report findings" isn't just true by
construction inside each report module, but also true when recomputed from the CSV a future data
store would actually load. Run after generate_reports.py, with the same conda env:

    conda activate rag-data-generator
    python dataGeneration/verify_origin.py [year]

Exits non-zero (and prints every mismatch) if any recomputed figure disagrees with the golden
JSON beyond a small floating-point tolerance.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def _load(report_id: str, year: int) -> tuple[pd.DataFrame, dict]:
    origin = pd.read_csv(OUTPUT_DIR / "origin" / f"{report_id}_FY{year}.csv")
    golden = json.load(open(OUTPUT_DIR / "golden" / f"{report_id}_FY{year}.json"))
    return origin, golden


def _check(label: str, actual: float, expected: float, errors: list[str], tol: float = 0.5) -> None:
    if not np.isclose(actual, expected, atol=tol):
        errors.append(f"{label}: recomputed {actual!r} != golden {expected!r}")


def verify_quarterly_sales(year: int, errors: list[str]) -> None:
    origin, golden = _load("01_quarterly_sales_performance", year)
    recomputed = origin.groupby(["Region", "Product", "Quarter"])["Order Amount"].sum() / 1000
    detail = pd.DataFrame(golden["tables"]["detail"]).set_index(["Region", "Product", "Quarter"])["Revenue"]
    for key, expected in detail.items():
        _check(f"quarterly_sales {key}", recomputed.get(key, 0.0), expected, errors)
    _check("quarterly_sales fy_total_revenue", origin["Order Amount"].sum() / 1000,
           golden["aggregates"]["fy_total_revenue"], errors)


def verify_product_profitability(year: int, errors: list[str]) -> None:
    origin, golden = _load("07_product_profitability", year)
    rev = origin.groupby("SKU")["Line Revenue"].sum() / 1000  # $ -> $k, matches golden's units
    cogs = origin.groupby("SKU")["Line COGS"].sum() / 1000
    units = origin.groupby("SKU")["Units"].sum()
    for row in golden["tables"]["detail"]:
        sku = row["SKU"]
        _check(f"product_profitability {sku} revenue", rev.get(sku, 0.0), row["Revenue"], errors)
        _check(f"product_profitability {sku} cogs", cogs.get(sku, 0.0), row["COGS"], errors)
        _check(f"product_profitability {sku} units", units.get(sku, 0), row["Units Sold"], errors, tol=0.6)


def verify_budget_vs_actual(year: int, errors: list[str]) -> None:
    origin, golden = _load("08_budget_vs_actual", year)
    actual_by_cc_q = origin.groupby(["Cost Center", "Quarter"])["Amount"].sum()
    for row in golden["tables"]["detail"]:
        cc = row["Cost Center"]
        for q in ["Q1", "Q2", "Q3", "Q4"]:
            _check(f"budget_vs_actual {cc} {q} actual", actual_by_cc_q.get((cc, q), 0.0), row[f"{q} Actual"], errors)


def verify_marketing_campaigns(year: int, errors: list[str]) -> None:
    origin, golden = _load("05_marketing_campaign_performance", year)
    by_campaign = origin.groupby("Campaign").agg(
        Impressions=("Impressions", "sum"), Clicks=("Clicks", "sum"),
        Spend=("Spend", "sum"), Conversions=("Conversions", "sum"),
    )
    for row in golden["tables"]["detail"]:
        c = row["Campaign"]
        r = by_campaign.loc[c]
        _check(f"marketing {c} impressions", r["Impressions"], row["Impressions"], errors, tol=1.5)
        _check(f"marketing {c} clicks", r["Clicks"], row["Clicks"], errors, tol=1.5)
        _check(f"marketing {c} spend", r["Spend"], row["Spend"], errors)
        _check(f"marketing {c} conversions", r["Conversions"], row["Conversions"], errors, tol=1.5)


def verify_travel_expenses(year: int, errors: list[str]) -> None:
    origin, golden = _load("09_travel_expense_report", year)
    by_dept = origin.groupby("Department")["Amount"].sum()
    for row in golden["tables"]["by_department"]:
        _check(f"travel_expenses dept {row['Department']}", by_dept.get(row["Department"], 0.0), row["Amount"], errors)
    _check("travel_expenses total", origin["Amount"].sum(), golden["aggregates"]["total_expenses"], errors)


def verify_regional_kpi_scorecard(year: int, errors: list[str]) -> None:
    origin, golden = _load("10_regional_kpi_scorecard", year)
    revenue_rows = origin[origin["Reading Type"] == "Daily Revenue"] if "Reading Type" in origin.columns else origin
    by_region_q = revenue_rows.groupby(["Region", "Quarter"])["Revenue Amount"].sum() / 1000  # $ -> $k
    for row in golden["tables"]["detail"]:
        key = (row["Region"], row["Quarter"])
        _check(f"regional_kpi {key} revenue", by_region_q.get(key, 0.0), row["Revenue"], errors, tol=1.0)


def verify_headcount(year: int, errors: list[str]) -> None:
    origin, golden = _load("03_hr_headcount_report", year)
    for row in golden["tables"]["detail"]:
        dept, loc = row["Department"], row["Location"]
        cell = origin[(origin["Department"] == dept) & (origin["Location"] == loc)]
        new_hires = (pd.to_datetime(cell["Hire Date"]).dt.year == year).sum()
        attrition = (pd.to_datetime(cell["Termination Date"], errors="coerce").dt.year == year).sum()
        _check(f"headcount {dept}/{loc} new hires", new_hires, row["New Hires"], errors, tol=0.6)
        _check(f"headcount {dept}/{loc} attrition", attrition, row["Attrition"], errors, tol=0.6)


def verify_inventory(year: int, errors: list[str]) -> None:
    origin, golden = _load("04_inventory_supply_chain", year)
    # Shipment/Adjustment quantities are already stored signed (negative) in the origin data —
    # net on-hand is just the sum, not receipts-minus-shipments (that would double-negate).
    net = origin.groupby("SKU")["Quantity"].sum()
    for row in golden["tables"]["detail"]:
        _check(f"inventory {row['SKU']} on hand", net.get(row["SKU"], 0.0), row["On Hand"], errors, tol=1.5)


def verify_churn_retention(year: int, errors: list[str]) -> None:
    origin, golden = _load("06_customer_churn_retention", year)
    by_month_seg = origin.groupby(["Month", "Segment", "Event Type"]).size()
    for row in golden["tables"]["detail"]:
        key_new = (row["Month"], row["Segment"], "Signup")
        key_churn = (row["Month"], row["Segment"], "Churn")
        _check(f"churn {row['Month']}/{row['Segment']} new", by_month_seg.get(key_new, 0), row["New Customers"], errors, tol=0.6)
        _check(f"churn {row['Month']}/{row['Segment']} churned", by_month_seg.get(key_churn, 0), row["Churned"], errors, tol=0.6)


VERIFIERS = {
    "quarterly_sales": verify_quarterly_sales,
    "product_profitability": verify_product_profitability,
    "budget_vs_actual": verify_budget_vs_actual,
    "marketing_campaigns": verify_marketing_campaigns,
    "travel_expenses": verify_travel_expenses,
    "regional_kpi_scorecard": verify_regional_kpi_scorecard,
    "headcount": verify_headcount,
    "inventory": verify_inventory,
    "churn_retention": verify_churn_retention,
    # financial_statement has no origin CSV by design — nothing to verify.
}


def main() -> int:
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
    errors: list[str] = []
    for name, fn in VERIFIERS.items():
        try:
            fn(year, errors)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: verifier raised {exc!r}")
        print(f"  checked {name}")

    if errors:
        print(f"\n{len(errors)} mismatch(es):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"\nAll origin CSVs reconcile with golden JSON for FY{year}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
