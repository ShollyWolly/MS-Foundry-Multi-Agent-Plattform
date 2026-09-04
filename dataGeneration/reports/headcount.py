"""HR Headcount Report — headcount, hires, and attrition by department and location."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from lib.common import DEPARTMENTS, base_context, make_faker
from lib.fiscal import fy_label, fy_year_start
from lib.groundtruth import write_ground_truth, write_origin_csv
from lib.narrative import generate_summary
from lib.noise import add_noise_columns, sequential_id
from lib.render import render_pdf
from lib.tables import dataframe_to_table

SEED = 3
DEPARTMENT = "hr"
REPORT_ID = "hr_headcount_report"
TITLE = "Quarterly Headcount Report"
LOCATIONS = ["Seattle", "Austin", "Dublin", "Singapore", "Sao Paulo"]


def generate(output_dir: Path, year: int) -> None:
    rng = np.random.default_rng(SEED + year)
    fake = make_faker(SEED + year)
    fy = fy_label(year)
    suffix = f"_{fy}"
    year_start = fy_year_start(year)
    year_end = year_start.replace(month=12, day=31)

    # Step 1: coarse Department x Location headcount/hires/attrition targets (same shape as
    # before) — these now act as targets the origin-level employee roster must reconcile to
    # exactly, not final numbers.
    cell_targets = []
    for dept in DEPARTMENTS:
        for loc in LOCATIONS:
            headcount = int(rng.integers(3, 60))
            hires = int(rng.integers(0, max(2, headcount // 6)))
            attrition = int(rng.integers(0, max(2, headcount // 8)))
            cell_targets.append((dept, loc, headcount, hires, attrition))

    # Step 2: explode each cell into individual employee roster rows.
    #   - `hires` rows: hired during the fiscal year, still active at EOQ.
    #   - `headcount - hires` rows: hired before the fiscal year, still active at EOQ.
    #   - `attrition` rows: hired before the fiscal year, terminated during the fiscal year.
    # Headcount (EOQ)/New Hires/Attrition are then derived FROM this roster by construction.
    origin_rows = []
    for dept, loc, headcount, hires, attrition in cell_targets:
        pre_existing = headcount - hires
        for _ in range(hires):
            hire_date = year_start + timedelta(days=int(rng.integers(0, 365)))
            origin_rows.append({
                "Department": dept,
                "Location": loc,
                "Hire Date": hire_date.isoformat(),
                "Termination Date": None,
            })
        for _ in range(pre_existing):
            hire_date = year_start - timedelta(days=int(rng.integers(30, 365 * 6)))
            origin_rows.append({
                "Department": dept,
                "Location": loc,
                "Hire Date": hire_date.isoformat(),
                "Termination Date": None,
            })
        for _ in range(attrition):
            hire_date = year_start - timedelta(days=int(rng.integers(30, 365 * 6)))
            term_date = year_start + timedelta(days=int(rng.integers(0, 365)))
            origin_rows.append({
                "Department": dept,
                "Location": loc,
                "Hire Date": hire_date.isoformat(),
                "Termination Date": term_date.isoformat(),
            })
    origin_df = pd.DataFrame(origin_rows)

    # Step 3: noise columns — realistic-looking but analytically inert.
    origin_df = add_noise_columns(origin_df, rng, fake, {
        "Employee ID": sequential_id("EMP", 200000),
        "Employee Name": lambda r, f, i: f.name(),
        "Job Title": lambda r, f, i: f.job(),
        "Manager Name": lambda r, f, i: f.name(),
    })
    origin_df = origin_df[[
        "Employee ID", "Employee Name", "Department", "Location", "Job Title", "Manager Name",
        "Hire Date", "Termination Date",
    ]]

    # Step 4: derive the report's tables FROM the roster (not independently generated).
    df = origin_df.groupby(["Department", "Location"]).apply(
        lambda g: pd.Series({
            "Headcount (EOQ)": int(g["Termination Date"].isna().sum()),
            "New Hires": int((g["Hire Date"] >= year_start.isoformat()).sum()),
            "Attrition": int(g["Termination Date"].notna().sum()),
        }),
        include_groups=False,
    ).reset_index()
    df["Net Change"] = df["New Hires"] - df["Attrition"]

    dept_summary = df.groupby("Department", as_index=False)[["Headcount (EOQ)", "New Hires", "Attrition"]].sum()
    dept_summary["Attrition Rate %"] = (dept_summary["Attrition"] / dept_summary["Headcount (EOQ)"] * 100).round(1)

    detail_table = dataframe_to_table(
        df, f"Table 2. Headcount Detail by Department and Location (Q1 {fy})",
        int_cols=("Headcount (EOQ)", "New Hires", "Attrition", "Net Change"),
    )
    summary_table = dataframe_to_table(
        dept_summary, "Table 1. Headcount Summary by Department",
        int_cols=("Headcount (EOQ)", "New Hires", "Attrition"),
        percent_cols=("Attrition Rate %",),
        total_row=False,
    )

    top_growth = dept_summary.sort_values("New Hires", ascending=False).iloc[0]
    highest_attrition = dept_summary.sort_values("Attrition Rate %", ascending=False).iloc[0]
    summary_text = generate_summary(
        f"Quarterly Headcount Report — Q1 {fy}",
        f"Total headcount: {int(df['Headcount (EOQ)'].sum())} across {len(DEPARTMENTS)} departments and "
        f"{len(LOCATIONS)} locations. Most new hires: {top_growth['Department']} ({int(top_growth['New Hires'])} hires). "
        f"Highest attrition rate: {highest_attrition['Department']} ({highest_attrition['Attrition Rate %']:.1f}%).",
        fallback=(
            "Total headcount grew modestly this quarter, with the strongest net additions in "
            "Engineering and Customer Success. Attrition remained within the target range across "
            "most departments, with the exception of Operations, which saw elevated turnover in "
            "the Sao Paulo location."
        ),
    )

    context = base_context(f"Quarterly Headcount Report — Q1 {fy}", year)
    context["sections"] = [
        {
            "heading": "Executive Summary",
            "narrative": [summary_text],
            "tables": [summary_table],
        },
        {
            "heading": "Headcount Detail by Department and Location",
            "narrative": [],
            "tables": [detail_table],
        },
    ]
    context["footnotes"] = [
        "Headcount (EOQ) reflects end-of-quarter active employee count, excluding contractors.",
        "Attrition Rate % is calculated as attrition divided by end-of-quarter headcount.",
    ]

    render_pdf(DEPARTMENT, context, output_dir / "raw" / f"03_hr_headcount_report{suffix}.pdf")
    write_ground_truth(
        output_dir / "golden" / f"03_hr_headcount_report{suffix}.json",
        {"detail": df, "by_department": dept_summary},
        {"total_headcount": int(df["Headcount (EOQ)"].sum())},
        report_id=REPORT_ID,
        report_title=TITLE,
        department=DEPARTMENT,
        year=year,
    )
    write_origin_csv(origin_df, output_dir / "origin" / f"03_hr_headcount_report{suffix}.csv")
