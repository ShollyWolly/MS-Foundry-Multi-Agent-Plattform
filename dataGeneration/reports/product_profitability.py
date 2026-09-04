"""Product Profitability Report — revenue, COGS, and margin by product."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from lib.common import base_context, make_faker
from lib.fiscal import fy_label, fy_year_start
from lib.groundtruth import write_ground_truth, write_origin_csv
from lib.narrative import generate_summary
from lib.noise import add_noise_columns, sequential_id
from lib.render import render_pdf
from lib.tables import dataframe_to_table

SEED = 7
DEPARTMENT = "product"
REPORT_ID = "product_profitability"
TITLE = "Product Profitability Report"
LINES = ["Insight Suite", "Forecast Pro", "DataFlow", "Analytics Hub", "PulseBI", "MetricWorks"]
SALES_CHANNELS = ["Direct Sales", "Self-Serve", "Reseller/Partner", "Marketplace"]


def generate(output_dir: Path, year: int) -> None:
    rng = np.random.default_rng(SEED + year)
    fake = make_faker(SEED + year)
    fy = fy_label(year)
    suffix = f"_{fy}"
    year_start = fy_year_start(year)

    # Step 1: coarse per-SKU revenue/COGS/units targets (same shape as before) — these now act
    # as targets the origin-level order line items must sum to exactly.
    skus = []
    for i in range(55):
        line = LINES[i % len(LINES)]
        revenue = round(rng.uniform(40, 900), 1)
        margin_pct = rng.uniform(35, 78)
        cogs = round(revenue * (1 - margin_pct / 100), 1)
        units = int(rng.integers(50, 5000))
        skus.append({
            "SKU": f"{line[:3].upper()}-{100 + i}",
            "Product Line": line,
            "Revenue": revenue,
            "COGS": cogs,
            "Units Sold": units,
        })

    # Step 2: explode each SKU's totals into individual order line items whose amounts sum
    # exactly to the SKU's target revenue/COGS/units (Dirichlet split per metric, same technique
    # as quarterly_sales.py).
    origin_rows = []
    for sku in skus:
        n_lines = int(rng.integers(10, 30))

        def split_int(total, n):
            weights = rng.dirichlet(np.ones(n))
            vals = np.floor(weights * total).astype(int)
            residual = int(total) - int(vals.sum())
            for idx in rng.choice(n, size=max(residual, 0), replace=(residual > n)):
                vals[idx] += 1
            return vals

        def split_float(total_k, n):
            weights = rng.dirichlet(np.ones(n))
            vals = np.round(weights * total_k * 1000, 2)  # $k target -> $ line-item grain
            vals[-1] += round(total_k * 1000 - vals.sum(), 2)
            return vals

        units_split = split_int(sku["Units Sold"], n_lines)
        revenue_split = split_float(sku["Revenue"], n_lines)
        cogs_split = split_float(sku["COGS"], n_lines)

        for j in range(n_lines):
            order_date = year_start + timedelta(days=int(rng.integers(0, 364)))
            origin_rows.append({
                "SKU": sku["SKU"],
                "Product Line": sku["Product Line"],
                "Order Date": order_date.isoformat(),
                "Units": int(units_split[j]),
                "Line Revenue": float(revenue_split[j]),
                "Line COGS": float(cogs_split[j]),
            })
    origin_df = pd.DataFrame(origin_rows)

    # Step 3: noise columns — realistic-looking but analytically inert.
    origin_df = add_noise_columns(origin_df, rng, fake, {
        "Order Line ID": sequential_id("OL", 700000),
        "Customer": lambda r, f, i: f.company(),
        "Sales Channel": lambda r, f, i: r.choice(SALES_CHANNELS),
        "Discount Code": lambda r, f, i: f.bothify("PROMO-###?"),
    })

    # Step 4: derive the report's tables FROM the origin data (not independently generated).
    df = origin_df.groupby(["SKU", "Product Line"], as_index=False)[
        ["Line Revenue", "Line COGS", "Units"]
    ].sum().rename(columns={"Line Revenue": "Revenue", "Line COGS": "COGS", "Units": "Units Sold"})
    df["Revenue"] = (df["Revenue"] / 1000).round(1)  # back to $k for report display
    df["COGS"] = (df["COGS"] / 1000).round(1)
    df["Gross Profit"] = (df["Revenue"] - df["COGS"]).round(1)
    df["Gross Margin %"] = (df["Gross Profit"] / df["Revenue"] * 100).round(1)
    df = df[["SKU", "Product Line", "Revenue", "COGS", "Gross Profit", "Gross Margin %", "Units Sold"]]

    by_line = df.groupby("Product Line", as_index=False)[["Revenue", "COGS", "Gross Profit"]].sum()
    by_line["Gross Margin %"] = (by_line["Gross Profit"] / by_line["Revenue"] * 100).round(1)

    detail_table = dataframe_to_table(
        df, "Table 2. SKU-Level Profitability Detail",
        currency_cols=("Revenue", "COGS", "Gross Profit"), percent_cols=("Gross Margin %",),
        int_cols=("Units Sold",), total_row=False,
    )
    line_table = dataframe_to_table(
        by_line.round(1), "Table 1. Profitability Summary by Product Line",
        currency_cols=("Revenue", "COGS", "Gross Profit"), percent_cols=("Gross Margin %",),
    )

    best_line = by_line.sort_values("Gross Margin %", ascending=False).iloc[0]
    worst_line = by_line.sort_values("Gross Margin %").iloc[0]
    summary_text = generate_summary(
        f"{TITLE} — {fy}",
        f"Portfolio total revenue: ${df['Revenue'].sum():,.0f}k, gross profit: ${df['Gross Profit'].sum():,.0f}k. "
        f"Highest-margin product line: {best_line['Product Line']} ({best_line['Gross Margin %']:.1f}%). "
        f"Lowest-margin product line: {worst_line['Product Line']} ({worst_line['Gross Margin %']:.1f}%).",
        fallback=(
            "Analytics Hub and Insight Suite continue to be the strongest contributors to gross "
            "profit, with margins above the portfolio average. Lower-margin SKUs are concentrated in "
            "the DataFlow line, reflecting higher infrastructure cost-to-serve."
        ),
    )

    context = base_context(f"{TITLE} — {fy}", year)
    context["kpi_tiles"] = [
        {"label": f"{fy} Revenue", "value": f"${df['Revenue'].sum():,.0f}k"},
        {"label": "Gross Profit", "value": f"${df['Gross Profit'].sum():,.0f}k"},
        {"label": "Best Margin", "value": best_line["Product Line"]},
    ]
    context["sections"] = [
        {
            "heading": "Executive Summary",
            "narrative": [summary_text],
            "tables": [line_table],
        },
        {
            "heading": "SKU-Level Detail",
            "narrative": [],
            "tables": [detail_table],
        },
    ]
    context["footnotes"] = [
        "Gross Margin % is calculated as Gross Profit divided by Revenue.",
        "All monetary figures are presented in USD thousands.",
    ]

    render_pdf(DEPARTMENT, context, output_dir / "raw" / f"07_product_profitability{suffix}.pdf")
    write_ground_truth(
        output_dir / "golden" / f"07_product_profitability{suffix}.json",
        {"detail": df, "by_product_line": by_line},
        report_id=REPORT_ID,
        report_title=TITLE,
        department=DEPARTMENT,
        year=year,
    )
    write_origin_csv(origin_df, output_dir / "origin" / f"07_product_profitability{suffix}.csv")
