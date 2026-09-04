"""Marketing Campaign Performance Report — spend, conversions, and ROAS by campaign."""
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

SEED = 5
DEPARTMENT = "marketing"
REPORT_ID = "marketing_campaign_performance"
TITLE = "Marketing Campaign Performance Report"
CHANNELS = ["Paid Search", "Paid Social", "Display", "Email", "Events/Field"]
PLACEMENTS = ["Desktop", "Mobile", "Tablet", "Connected TV"]


def generate(output_dir: Path, year: int) -> None:
    rng = np.random.default_rng(SEED + year)
    fake = make_faker(SEED + year)
    fy = fy_label(year)
    suffix = f"_{fy}"

    # Step 1: coarse per-campaign totals (same shape as before) — these now act as targets the
    # origin-level daily performance data must sum to exactly.
    campaigns = []
    for i in range(45):
        channel = CHANNELS[i % len(CHANNELS)]
        impressions = int(rng.integers(20_000, 2_000_000))
        ctr = rng.uniform(0.4, 4.5)
        clicks = int(impressions * ctr / 100)
        spend = round(rng.uniform(2_000, 80_000), 0)
        conv_rate = rng.uniform(0.5, 8.0)
        conversions = max(1, int(clicks * conv_rate / 100))
        revenue = round(conversions * rng.uniform(150, 900), 0)
        campaigns.append({
            "Campaign": f"{channel} — {fake.catch_phrase()}"[:40],
            "Channel": channel,
            "Impressions": impressions,
            "Clicks": clicks,
            "Spend": spend,
            "Conversions": conversions,
            "Revenue": revenue,
        })

    # Step 2: explode each campaign's totals into daily rows over the fiscal year whose sums
    # match the campaign totals exactly (Dirichlet split per metric, same technique as
    # quarterly_sales.py, applied independently to each additive metric column).
    year_start = fy_year_start(year)
    n_days = 365
    origin_rows = []
    for camp in campaigns:
        n_active_days = int(rng.integers(60, n_days))
        active_offsets = rng.choice(n_days, size=n_active_days, replace=False)
        active_offsets.sort()

        def split(total, n, is_int):
            weights = rng.dirichlet(np.ones(n))
            vals = weights * total
            if is_int:
                vals = np.floor(vals).astype(int)
                residual = int(total) - int(vals.sum())
                # hand out remaining units one at a time to random rows
                idxs = rng.choice(n, size=max(residual, 0), replace=(residual > n))
                for idx in idxs:
                    vals[idx] += 1
            else:
                vals = np.round(vals, 2)
                vals[-1] += round(total - vals.sum(), 2)
            return vals

        impressions_split = split(camp["Impressions"], n_active_days, True)
        clicks_split = split(camp["Clicks"], n_active_days, True)
        spend_split = split(camp["Spend"], n_active_days, False)
        conversions_split = split(camp["Conversions"], n_active_days, True)
        revenue_split = split(camp["Revenue"], n_active_days, False)

        for j, offset in enumerate(active_offsets):
            event_date = year_start + timedelta(days=int(offset))
            origin_rows.append({
                "Campaign": camp["Campaign"],
                "Channel": camp["Channel"],
                "Date": event_date.isoformat(),
                "Impressions": int(impressions_split[j]),
                "Clicks": int(clicks_split[j]),
                "Spend": float(spend_split[j]),
                "Conversions": int(conversions_split[j]),
                "Revenue": float(revenue_split[j]),
            })
    origin_df = pd.DataFrame(origin_rows)

    # Step 3: noise columns — realistic-looking but analytically inert.
    origin_df = add_noise_columns(origin_df, rng, fake, {
        "Event ID": sequential_id("MKT", 500000),
        "Ad Creative": lambda r, f, i: f.catch_phrase(),
        "Placement/Device": lambda r, f, i: r.choice(PLACEMENTS),
        "Account Manager": lambda r, f, i: f.name(),
    })

    # Step 4: derive the report's tables FROM the origin data (not independently generated).
    df = origin_df.groupby(["Campaign", "Channel"], as_index=False)[
        ["Impressions", "Clicks", "Spend", "Conversions", "Revenue"]
    ].sum()
    df["CTR %"] = (df["Clicks"] / df["Impressions"] * 100).round(2)
    df["CPA"] = (df["Spend"] / df["Conversions"]).round(2)
    df["ROAS"] = (df["Revenue"] / df["Spend"]).round(2)
    df["Spend"] = df["Spend"].round(0)
    df["Revenue"] = df["Revenue"].round(0)
    df = df[["Campaign", "Channel", "Impressions", "Clicks", "CTR %", "Spend", "Conversions", "CPA", "ROAS"]]

    by_channel = df.groupby("Channel", as_index=False)[["Spend", "Conversions"]].sum()
    by_channel["Blended CPA"] = (by_channel["Spend"] / by_channel["Conversions"]).round(2)

    detail_table = dataframe_to_table(
        df, "Table 2. Campaign-Level Performance Detail",
        currency_cols=("Spend", "CPA"), percent_cols=("CTR %",), int_cols=("Impressions", "Clicks", "Conversions"),
        total_row=False,
    )
    channel_table = dataframe_to_table(
        by_channel, "Table 1. Performance Summary by Channel",
        currency_cols=("Spend", "Blended CPA"), int_cols=("Conversions",),
    )

    best_channel = by_channel.sort_values("Blended CPA").iloc[0]
    summary_text = generate_summary(
        f"{TITLE} — {fy}",
        f"Total spend: ${df['Spend'].sum():,.0f} across {len(df)} campaigns and {len(CHANNELS)} channels "
        f"({', '.join(CHANNELS)}). Total conversions: {int(df['Conversions'].sum())}. "
        f"Most efficient channel by blended CPA: {best_channel['Channel']} (${best_channel['Blended CPA']:,.2f}).",
        fallback=(
            "Paid Search and Paid Social continue to deliver the strongest return on ad spend this "
            "fiscal year, while Display campaigns show elevated CPA relative to target. Overall blended "
            "CPA improved versus the prior year as budget was reallocated toward higher-performing "
            "channels."
        ),
    )

    context = base_context(f"{TITLE} — {fy}", year)
    context["kpi_tiles"] = [
        {"label": "Total Spend", "value": f"${df['Spend'].sum():,.0f}"},
        {"label": "Conversions", "value": f"{int(df['Conversions'].sum()):,}"},
        {"label": "Best Channel (CPA)", "value": best_channel["Channel"]},
    ]
    context["sections"] = [
        {
            "heading": "Executive Summary",
            "narrative": [summary_text],
            "tables": [channel_table],
        },
        {
            "heading": "Campaign Detail",
            "narrative": [],
            "tables": [detail_table],
        },
    ]
    context["footnotes"] = [
        "ROAS (Return on Ad Spend) is calculated as attributed revenue divided by media spend.",
        "CPA (Cost per Acquisition) is calculated as media spend divided by conversions.",
    ]

    render_pdf(DEPARTMENT, context, output_dir / "raw" / f"05_marketing_campaign_performance{suffix}.pdf")
    write_ground_truth(
        output_dir / "golden" / f"05_marketing_campaign_performance{suffix}.json",
        {"detail": df, "by_channel": by_channel},
        {"total_spend": float(df["Spend"].sum()), "total_conversions": int(df["Conversions"].sum())},
        report_id=REPORT_ID,
        report_title=TITLE,
        department=DEPARTMENT,
        year=year,
    )
    write_origin_csv(origin_df, output_dir / "origin" / f"05_marketing_campaign_performance{suffix}.csv")
