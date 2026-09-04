"""Travel & Expense Report — individual expense line items across employees."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from lib.common import DEPARTMENTS, base_context, make_faker
from lib.fiscal import fy_quarter_label, fy_year_start
from lib.groundtruth import write_ground_truth, write_origin_csv
from lib.narrative import generate_summary
from lib.noise import add_noise_columns, sequential_id
from lib.render import render_pdf
from lib.tables import dataframe_to_table

SEED = 9
DEPARTMENT = "admin"
REPORT_ID = "travel_expense_report"
TITLE = "Travel & Expense Report"
CATEGORIES = ["Airfare", "Lodging", "Ground Transport", "Meals", "Client Entertainment", "Conference Fees", "Other"]


def generate(output_dir: Path, year: int) -> None:
    rng = np.random.default_rng(SEED + year)
    fake = make_faker(SEED + year)
    quarter_label = fy_quarter_label(year, 0)  # this report is framed as "Q1" only
    suffix = f"_FY{year}"
    start_date = fy_year_start(year)

    employees = [(fake.name(), rng.choice(DEPARTMENTS)) for _ in range(28)]

    rows = []
    for name, dept in employees:
        for _ in range(int(rng.integers(2, 7))):
            category = rng.choice(CATEGORIES)
            amount_ranges = {
                "Airfare": (180, 1400), "Lodging": (90, 650), "Ground Transport": (15, 180),
                "Meals": (10, 150), "Client Entertainment": (40, 400), "Conference Fees": (200, 2200),
                "Other": (10, 300),
            }
            lo, hi = amount_ranges[category]
            amount = round(rng.uniform(lo, hi), 2)
            offset = int(rng.integers(0, 90))
            rows.append({
                "Employee": name,
                "Department": dept,
                "Date": (start_date + timedelta(days=offset)).isoformat(),
                "Category": category,
                "Description": fake.bs().capitalize(),
                "Amount": amount,
            })
    df = pd.DataFrame(rows).sort_values(["Department", "Employee", "Date"]).reset_index(drop=True)

    # Noise columns — realistic-looking but analytically inert.
    df = add_noise_columns(df, rng, fake, {
        "Expense Report ID": sequential_id("ER", 500000),
        "Approval Status": lambda r, f, i: r.choice(
            ["Approved", "Approved", "Approved", "Approved", "Pending", "Rejected"]
        ),
        "Payment Method": lambda r, f, i: r.choice(["Corporate Card", "Personal Card (Reimbursed)", "Cash Advance"]),
        "Merchant": lambda r, f, i: f.company(),
    })

    by_dept = df.groupby("Department", as_index=False)["Amount"].sum().sort_values("Amount", ascending=False)
    by_category = df.groupby("Category", as_index=False)["Amount"].sum().sort_values("Amount", ascending=False)

    detail_table = dataframe_to_table(
        df, f"Table 3. Expense Line-Item Detail, {quarter_label}", currency_cols=("Amount",),
    )
    dept_table = dataframe_to_table(
        by_dept.round(2), "Table 1. Total Expenses by Department", currency_cols=("Amount",),
    )
    category_table = dataframe_to_table(
        by_category.round(2), "Table 2. Total Expenses by Category", currency_cols=("Amount",),
    )

    top_category = by_category.iloc[0]
    top_dept = by_dept.iloc[0]
    summary_text = generate_summary(
        f"Travel & Expense Report — {quarter_label}",
        f"Total {quarter_label} T&E spend: ${df['Amount'].sum():,.0f} across {len(employees)} employees. "
        f"Largest expense category: {top_category['Category']} (${top_category['Amount']:,.0f}). "
        f"Highest-spending department: {top_dept['Department']} (${top_dept['Amount']:,.0f}).",
        fallback=(
            "This report summarizes travel and expense submissions for the first quarter of fiscal "
            f"{year}. Airfare and Conference Fees represent the largest expense categories, consistent "
            "with planned attendance at industry events during the quarter."
        ),
    )

    context = base_context(f"Travel & Expense Report — {quarter_label}", year)
    context["sections"] = [
        {
            "heading": "Executive Summary",
            "narrative": [summary_text],
            "tables": [dept_table, category_table],
        },
        {
            "heading": "Expense Line-Item Detail",
            "narrative": [],
            "tables": [detail_table],
        },
    ]
    context["footnotes"] = [
        "All amounts are presented in USD and reflect submitted, manager-approved expense reports.",
        f"Report reflects expenses with submission dates between January 1 and March 31, {year}.",
    ]

    render_pdf(DEPARTMENT, context, output_dir / "raw" / f"09_travel_expense_report{suffix}.pdf")
    write_ground_truth(
        output_dir / "golden" / f"09_travel_expense_report{suffix}.json",
        {"detail": df, "by_department": by_dept, "by_category": by_category},
        {"total_expenses": float(df["Amount"].sum())},
        report_id=REPORT_ID,
        report_title=TITLE,
        department=DEPARTMENT,
        year=year,
    )
    write_origin_csv(df, output_dir / "origin" / f"09_travel_expense_report{suffix}.csv")
