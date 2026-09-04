"""Quarterly Sales Performance Report — revenue by region, product, and quarter."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from lib.common import REGIONS, QUARTERS, base_context, make_faker
from lib.fiscal import fy_label, fy_year_start
from lib.groundtruth import write_ground_truth, write_origin_csv
from lib.narrative import generate_summary
from lib.noise import add_noise_columns, sequential_id
from lib.render import render_pdf
from lib.tables import dataframe_to_table

PRODUCTS = ["Insight Suite", "Forecast Pro", "DataFlow", "Analytics Hub", "PulseBI", "MetricWorks"]
SEED = 1
DEPARTMENT = "sales"
REPORT_ID = "quarterly_sales_performance"
TITLE = "Quarterly Sales Performance Report"


def generate(output_dir: Path, year: int) -> None:
    rng = np.random.default_rng(SEED + year)
    fake = make_faker(SEED + year)
    fy = fy_label(year)
    suffix = f"_{fy}"

    # Step 1: coarse Region x Product x Quarter revenue targets (same shape as before) — these
    # now act as targets the origin-level order data must sum to exactly, not final numbers.
    cell_targets = []
    for region in REGIONS:
        region_factor = rng.uniform(0.8, 1.4)
        for product in PRODUCTS:
            base = rng.uniform(80, 400) * region_factor
            for qi, q in enumerate(QUARTERS):
                growth = 1 + (0.02 * qi) + rng.normal(0, 0.05)
                cell_targets.append((region, product, q, qi, round(base * growth, 1)))

    # Step 2: explode each cell into individual order line items whose amounts sum exactly to
    # the cell's target revenue (a Dirichlet split keeps individual amounts varied/plausible
    # while guaranteeing the origin data aggregates back to the report findings by construction).
    year_start = fy_year_start(year)
    origin_rows = []
    for region, product, q, qi, target_k in cell_targets:
        n_orders = int(rng.integers(8, 20))
        weights = rng.dirichlet(np.ones(n_orders))
        amounts = np.round(weights * target_k * 1000, 2)  # $k target -> $ line-item grain
        amounts[-1] += round(target_k * 1000 - amounts.sum(), 2)  # fix rounding residual
        quarter_start = year_start.replace(month=qi * 3 + 1)
        for amt in amounts:
            order_date = quarter_start + timedelta(days=int(rng.integers(0, 89)))
            origin_rows.append({
                "Region": region,
                "Product": product,
                "Quarter": q,
                "Order Date": order_date.isoformat(),
                "Order Amount": float(amt),
            })
    origin_df = pd.DataFrame(origin_rows)

    # Step 3: noise columns — realistic-looking but analytically inert.
    origin_df = add_noise_columns(origin_df, rng, fake, {
        "Order ID": sequential_id("SO", 100000),
        "Sales Rep": lambda r, f, i: f.name(),
        "Customer": lambda r, f, i: f.company(),
        "Payment Method": lambda r, f, i: r.choice(["Wire Transfer", "ACH", "Credit Card", "Check"]),
        "Order Notes": lambda r, f, i: f.bs().capitalize(),
    })

    # Step 4: derive the report's tables FROM the origin data (not independently generated) —
    # guarantees consistency between the origin CSV and the PDF/golden JSON.
    detail_df = origin_df.groupby(["Region", "Product", "Quarter"], as_index=False)["Order Amount"].sum() \
        .rename(columns={"Order Amount": "Revenue"})
    detail_df["Revenue"] = (detail_df["Revenue"] / 1000).round(1)  # back to $k for report display

    pivot = detail_df.pivot_table(index=["Region", "Product"], columns="Quarter", values="Revenue", aggfunc="sum")
    pivot = pivot[QUARTERS].reset_index()
    pivot["FY Total"] = pivot[QUARTERS].sum(axis=1)
    prior_fy_estimate = pivot["FY Total"] / rng.uniform(1.02, 1.15, len(pivot))
    pivot["YoY %"] = ((pivot["FY Total"] / prior_fy_estimate) - 1) * 100

    summary = detail_df.groupby("Region", as_index=False)["Revenue"].sum().rename(columns={"Revenue": "FY Total"})
    summary = summary.sort_values("FY Total", ascending=False)

    detail_table = dataframe_to_table(
        pivot.round(1),
        f"Table 2. Revenue by Region and Product, {fy} (USD thousands)",
        currency_cols=("Q1", "Q2", "Q3", "Q4", "FY Total"),
        percent_cols=("YoY %",),
        header_groups=[
            {"label": "", "colspan": 2},
            {"label": f"{fy} Revenue by Quarter", "colspan": 4},
            {"label": "", "colspan": 2},
        ],
        total_row=True,
    )
    summary_table = dataframe_to_table(
        summary.round(1),
        f"Table 1. {fy} Revenue by Region (USD thousands)",
        currency_cols=("FY Total",),
    )

    top_region = summary.iloc[0]
    summary_text = generate_summary(
        f"{TITLE} — {fy}",
        f"Total {fy} revenue across all regions: ${detail_df['Revenue'].sum():,.0f}k. "
        f"Top-performing region: {top_region['Region']} (${top_region['FY Total']:,.0f}k). "
        f"Products sold: {', '.join(PRODUCTS)}. Regions covered: {', '.join(REGIONS)}. "
        f"Average YoY growth across region/product lines: {pivot['YoY %'].mean():.1f}%.",
        fallback=(
            f"This report summarizes revenue performance across all regions and product lines for "
            f"fiscal year {year}. Overall bookings grew across most regions, with continued strength in "
            "the Analytics Hub and Insight Suite product lines. Regional variance reflects differences "
            "in market maturity and go-to-market investment."
        ),
    )

    context = base_context(f"{TITLE} — {fy}", year)
    context["kpi_tiles"] = [
        {"label": f"{fy} Revenue", "value": f"${detail_df['Revenue'].sum():,.0f}k"},
        {"label": "Top Region", "value": top_region["Region"]},
        {"label": "Avg YoY Growth", "value": f"{pivot['YoY %'].mean():.1f}%"},
    ]
    context["sections"] = [
        {
            "heading": "Executive Summary",
            "narrative": [summary_text],
            "tables": [summary_table],
        },
        {
            "heading": "Revenue Detail by Region and Product",
            "narrative": [
                "The table below breaks down quarterly revenue by region and product, including "
                "full-year totals and year-over-year growth versus the prior fiscal year.",
            ],
            "tables": [detail_table],
        },
    ]
    context["footnotes"] = [
        "All figures are presented in USD thousands unless otherwise noted.",
        "YoY % is calculated against an estimated prior fiscal year baseline and may be subject to restatement.",
    ]

    render_pdf(DEPARTMENT, context, output_dir / "raw" / f"01_quarterly_sales_performance{suffix}.pdf")
    write_ground_truth(
        output_dir / "golden" / f"01_quarterly_sales_performance{suffix}.json",
        {"detail": detail_df, "by_region_product": pivot, "by_region": summary},
        {"fy_total_revenue": float(detail_df["Revenue"].sum())},
        report_id=REPORT_ID,
        report_title=TITLE,
        department=DEPARTMENT,
        year=year,
    )
    write_origin_csv(origin_df, output_dir / "origin" / f"01_quarterly_sales_performance{suffix}.csv")
