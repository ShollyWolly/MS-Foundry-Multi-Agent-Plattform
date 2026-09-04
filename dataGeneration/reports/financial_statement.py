"""Annual Financial Statement Excerpt — income statement, balance sheet, cash flow (3-year)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from lib.common import base_context, make_faker
from lib.fiscal import fy_label, trailing_fy_labels
from lib.groundtruth import write_ground_truth
from lib.narrative import generate_summary
from lib.render import render_pdf
from lib.tables import dataframe_to_table

SEED = 2
DEPARTMENT = "finance"
REPORT_ID = "annual_financial_statement"
TITLE = "Annual Financial Statement Excerpt"

INCOME_LINES = [
    "Product Revenue", "Services Revenue", "Total Revenue", "Cost of Revenue", "Gross Profit",
    "Sales & Marketing", "Research & Development", "General & Administrative",
    "Total Operating Expenses", "Operating Income", "Interest Expense", "Tax Expense", "Net Income",
]
BALANCE_LINES = [
    "Cash & Equivalents", "Accounts Receivable", "Inventory", "Total Current Assets",
    "Property & Equipment", "Goodwill & Intangibles", "Total Assets",
    "Accounts Payable", "Accrued Liabilities", "Total Current Liabilities",
    "Long-Term Debt", "Total Liabilities", "Total Shareholders' Equity",
]
CASHFLOW_LINES = [
    "Net Income", "Depreciation & Amortization", "Change in Working Capital",
    "Cash from Operating Activities", "Capital Expenditures", "Cash from Investing Activities",
    "Debt Repayment", "Cash from Financing Activities", "Net Change in Cash",
]


def _build_statement(rng, lines: list[str], base_range: tuple[float, float], growth_range: tuple[float, float], years: list[str]) -> pd.DataFrame:
    data = {"Line Item": lines}
    base = rng.uniform(*base_range, len(lines))
    for i, year in enumerate(years):
        growth = rng.uniform(*growth_range, len(lines)) ** i
        data[year] = np.round(base * growth, 1)
    return pd.DataFrame(data)


def generate(output_dir: Path, year: int) -> None:
    rng = np.random.default_rng(SEED + year)
    make_faker(SEED + year)
    fy = fy_label(year)
    suffix = f"_{fy}"
    years = trailing_fy_labels(year, 3)

    income_df = _build_statement(rng, INCOME_LINES, (500, 8000), (1.03, 1.18), years)
    balance_df = _build_statement(rng, BALANCE_LINES, (300, 6000), (1.02, 1.15), years)
    cashflow_df = _build_statement(rng, CASHFLOW_LINES, (200, 3000), (0.95, 1.20), years)

    income_table = dataframe_to_table(
        income_df, "Table 1. Consolidated Income Statement (USD thousands)",
        currency_cols=tuple(years), total_row=False,
    )
    balance_table = dataframe_to_table(
        balance_df, "Table 2. Consolidated Balance Sheet (USD thousands)",
        currency_cols=tuple(years), total_row=False,
    )
    cashflow_table = dataframe_to_table(
        cashflow_df, "Table 3. Consolidated Statement of Cash Flows (USD thousands)",
        currency_cols=tuple(years), total_row=False,
    )

    revenue_row = income_df[income_df["Line Item"] == "Total Revenue"].iloc[0]
    net_income_row = income_df[income_df["Line Item"] == "Net Income"].iloc[0]
    summary_text = generate_summary(
        f"Annual Financial Statement Excerpt — {fy}",
        f"Total Revenue by year: {years[0]} ${revenue_row[years[0]]:,.0f}k, {years[1]} ${revenue_row[years[1]]:,.0f}k, "
        f"{years[2]} ${revenue_row[years[2]]:,.0f}k. Net Income {years[2]}: ${net_income_row[years[2]]:,.0f}k "
        f"({years[0]}: ${net_income_row[years[0]]:,.0f}k). This is a condensed three-statement excerpt "
        "(income statement, balance sheet, cash flow).",
        fallback=(
            "This excerpt presents a condensed, three-year view of the company's consolidated "
            "income statement, balance sheet, and cash flow statement. Figures are unaudited and "
            "prepared for internal management reporting purposes only."
        ),
    )

    context = base_context(f"Annual Financial Statement Excerpt — {fy}", year)
    context["sections"] = [
        {
            "heading": "Executive Summary",
            "narrative": [summary_text],
            "tables": [],
        },
        {"heading": "Income Statement", "narrative": [], "tables": [income_table]},
        {"heading": "Balance Sheet", "narrative": [], "tables": [balance_table]},
        {"heading": "Statement of Cash Flows", "narrative": [], "tables": [cashflow_table]},
    ]
    context["footnotes"] = [
        "Figures are unaudited and presented in USD thousands unless otherwise noted.",
        "Prior-year figures may differ from previously published statements due to reclassification.",
    ]

    render_pdf(DEPARTMENT, context, output_dir / "raw" / f"02_annual_financial_statement{suffix}.pdf")
    write_ground_truth(
        output_dir / "golden" / f"02_annual_financial_statement{suffix}.json",
        {"income_statement": income_df, "balance_sheet": balance_df, "cash_flow": cashflow_df},
        report_id=REPORT_ID,
        report_title=TITLE,
        department=DEPARTMENT,
        year=year,
    )
