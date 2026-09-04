"""Budget vs. Actual Report — quarterly budget/actual/variance by cost center."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from lib.common import QUARTERS, base_context, make_faker
from lib.fiscal import fy_label, fy_year_start
from lib.groundtruth import write_ground_truth, write_origin_csv
from lib.narrative import generate_summary
from lib.noise import add_noise_columns, sequential_id
from lib.render import render_pdf
from lib.tables import dataframe_to_table

SEED = 8
DEPARTMENT = "finance"
REPORT_ID = "budget_vs_actual"
TITLE = "Budget vs. Actual Report"
COST_CENTERS = [
    "Sales — North America", "Sales — EMEA", "Sales — APAC", "Marketing — Brand",
    "Marketing — Demand Gen", "Engineering — Platform", "Engineering — Applied AI",
    "Product Management", "Customer Success", "Finance & Accounting", "Human Resources",
    "IT & Security", "Facilities", "Legal & Compliance", "Executive & G&A",
    "Operations — Supply Chain", "Customer Support", "Data & Analytics",
    "Partnerships & Alliances", "Corporate Development",
]


def generate(output_dir: Path, year: int) -> None:
    rng = np.random.default_rng(SEED + year)
    fake = make_faker(SEED + year)
    fy = fy_label(year)
    suffix = f"_{fy}"
    year_start = fy_year_start(year)

    # Step 1: per-cost-center per-quarter budget (a planning figure — no transactional origin)
    # and target actual spend (the origin-level GL expense line items below must net to this
    # exactly).
    cell_targets = []
    budget_rows = []
    for cc in COST_CENTERS:
        row = {"Cost Center": cc}
        for qi, q in enumerate(QUARTERS):
            budget = round(rng.uniform(80, 900), 1)
            actual_target = round(budget * rng.uniform(0.85, 1.20), 1)
            row[f"{q} Budget"] = budget
            cell_targets.append((cc, q, qi, actual_target))
        budget_rows.append(row)

    # Step 2: explode each cost center/quarter's target actual spend into individual GL expense
    # line items whose amounts net exactly to that target (Dirichlet split, same technique as
    # quarterly_sales.py).
    origin_rows = []
    for cc, q, qi, target_k in cell_targets:
        n_txns = int(rng.integers(6, 18))
        weights = rng.dirichlet(np.ones(n_txns))
        amounts = np.round(weights * target_k * 1000, 2)  # $k target -> $ line-item grain
        amounts[-1] += round(target_k * 1000 - amounts.sum(), 2)
        quarter_start = year_start.replace(month=qi * 3 + 1)
        for amt in amounts:
            txn_date = quarter_start + timedelta(days=int(rng.integers(0, 89)))
            origin_rows.append({
                "Cost Center": cc,
                "Quarter": q,
                "Transaction Date": txn_date.isoformat(),
                "Amount": float(amt),
            })
    origin_df = pd.DataFrame(origin_rows)

    # Step 3: noise columns — realistic-looking but analytically inert.
    origin_df = add_noise_columns(origin_df, rng, fake, {
        "Transaction ID": sequential_id("GL", 800000),
        "Vendor": lambda r, f, i: f.company(),
        "GL Account Description": lambda r, f, i: f.bs().capitalize(),
        "Approved By": lambda r, f, i: f.name(),
    })

    # Step 4: derive Actual spend FROM the origin data (not independently generated); Budget
    # stays a planning figure with no transactional origin.
    actual_by_cc_q = origin_df.groupby(["Cost Center", "Quarter"], as_index=False)["Amount"].sum()
    actual_by_cc_q["Amount"] = actual_by_cc_q["Amount"].round(1)

    budget_df = pd.DataFrame(budget_rows)
    df = budget_df.copy()
    fy_budget = np.zeros(len(df))
    fy_actual = np.zeros(len(df))
    for qi, q in enumerate(QUARTERS):
        actual_col = actual_by_cc_q[actual_by_cc_q["Quarter"] == q].set_index("Cost Center")["Amount"]
        df[f"{q} Actual"] = df["Cost Center"].map(actual_col).round(1)
        fy_budget += df[f"{q} Budget"].to_numpy()
        fy_actual += df[f"{q} Actual"].to_numpy()
    df["FY Budget"] = np.round(fy_budget, 1)
    df["FY Actual"] = np.round(fy_actual, 1)
    df["Variance %"] = ((df["FY Actual"] / df["FY Budget"] - 1) * 100).round(1)

    ordered_cols = ["Cost Center"]
    for q in QUARTERS:
        ordered_cols += [f"{q} Budget", f"{q} Actual"]
    ordered_cols += ["FY Budget", "FY Actual", "Variance %"]
    df = df[ordered_cols]

    currency_cols = tuple(c for c in df.columns if c != "Cost Center" and c != "Variance %")
    header_groups = [{"label": "", "colspan": 1}]
    for q in QUARTERS:
        header_groups.append({"label": q, "colspan": 2})
    header_groups.append({"label": "Full Year", "colspan": 3})

    detail_table = dataframe_to_table(
        df, f"Table 1. Budget vs. Actual Spend by Cost Center, {fy} (USD thousands)",
        currency_cols=currency_cols, percent_cols=("Variance %",),
        header_groups=header_groups,
    )

    over_budget = df[df["Variance %"] > 5][["Cost Center", "Variance %"]].sort_values("Variance %", ascending=False)
    over_table = dataframe_to_table(
        over_budget.round(1), "Table 2. Cost Centers Exceeding Budget by More Than 5%",
        percent_cols=("Variance %",), total_row=False,
    )

    summary_text = generate_summary(
        f"{TITLE} — {fy}",
        f"Total {fy} budget: ${df['FY Budget'].sum():,.0f}k, actual spend: ${df['FY Actual'].sum():,.0f}k "
        f"({(df['FY Actual'].sum()/df['FY Budget'].sum()-1)*100:+.1f}% variance). "
        f"{len(over_budget)} of {len(COST_CENTERS)} cost centers exceeded budget by more than 5%, "
        f"the largest being {over_budget.iloc[0]['Cost Center']} at {over_budget.iloc[0]['Variance %']:+.1f}%."
        if len(over_budget) > 0 else
        f"Total {fy} budget: ${df['FY Budget'].sum():,.0f}k, actual spend: ${df['FY Actual'].sum():,.0f}k. "
        "No cost centers exceeded budget by more than 5%.",
        fallback=(
            "Full-year actual spend tracked closely to budget across most cost centers. Cost centers "
            "exceeding budget by more than 5% are called out separately below for management review."
        ),
    )

    context = base_context(f"{TITLE} — {fy}", year)
    context["sections"] = [
        {
            "heading": "Executive Summary",
            "narrative": [summary_text],
            "tables": [over_table],
        },
        {
            "heading": "Quarterly Budget vs. Actual Detail",
            "narrative": [],
            "tables": [detail_table],
        },
    ]
    context["footnotes"] = [
        "Variance % is calculated as (Full Year Actual / Full Year Budget - 1) x 100.",
        "All monetary figures are presented in USD thousands.",
    ]

    render_pdf(DEPARTMENT, context, output_dir / "raw" / f"08_budget_vs_actual{suffix}.pdf")
    write_ground_truth(
        output_dir / "golden" / f"08_budget_vs_actual{suffix}.json",
        {"detail": df, "over_budget": over_budget},
        report_id=REPORT_ID,
        report_title=TITLE,
        department=DEPARTMENT,
        year=year,
    )
    write_origin_csv(origin_df, output_dir / "origin" / f"08_budget_vs_actual{suffix}.csv")
