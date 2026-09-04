"""Regional KPI Scorecard — key business metrics by region and quarter."""
from __future__ import annotations

from datetime import date, timedelta
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

SEED = 10
DEPARTMENT = "executive"
REPORT_ID = "regional_kpi_scorecard"
TITLE = "Regional KPI Scorecard"
DATA_SOURCES = ["Salesforce", "NetSuite", "Zendesk", "HubSpot"]


def generate(output_dir: Path, year: int) -> None:
    rng = np.random.default_rng(SEED + year)
    fake = make_faker(SEED + year)
    fy = fy_label(year)
    suffix = f"_{fy}"
    year_start = fy_year_start(year)

    # This scorecard's metrics are mostly composite/derived ratios (Churn %, CAC, LTV) rather
    # than raw ledger data, so — per plan — its origin table is deliberately lighter-weight than
    # the transactional-explosion pattern used elsewhere: daily revenue readings (which sum back
    # to the quarterly Revenue figure) plus occasional NPS/CSAT survey-sample readings (which
    # average back to the quarterly NPS/CSAT figures). Churn %/CAC/LTV/Revenue Growth % stay
    # quarter-level composite figures with no per-reading origin.
    reading_rows = []
    report_rows = []
    for region in REGIONS:
        region_factor = rng.uniform(0.85, 1.3)
        prev_revenue = None
        for qi, q in enumerate(QUARTERS):
            quarter_start = year_start.replace(month=qi * 3 + 1)
            next_start = year_start.replace(month=(qi + 1) * 3 + 1) if qi < 3 else date(year + 1, 1, 1)
            days_in_quarter = (next_start - quarter_start).days

            # Daily revenue readings ($k) summing exactly to the quarter's revenue target via a
            # Dirichlet split (same technique as quarterly_sales.py).
            revenue_target_k = round(rng.uniform(600, 3200) * region_factor, 1)
            weights = rng.dirichlet(np.ones(days_in_quarter))
            daily_amounts = np.round(weights * revenue_target_k * 1000, 2)  # $k -> $ reading grain
            daily_amounts[-1] += round(revenue_target_k * 1000 - daily_amounts.sum(), 2)
            for d in range(days_in_quarter):
                reading_date = quarter_start + timedelta(days=d)
                reading_rows.append({
                    "Region": region, "Quarter": q, "Date": reading_date.isoformat(),
                    "Reading Type": "Daily Revenue",
                    "Revenue Amount": float(daily_amounts[d]), "NPS Score": np.nan, "CSAT Score": np.nan,
                })
            quarter_revenue = round(float(daily_amounts.sum()) / 1000, 1)

            # Occasional NPS/CSAT survey-sample readings — the quarterly NPS/CSAT figures are the
            # (rounded) mean of these samples, so they average back by construction.
            n_nps = int(rng.integers(6, 12))
            nps_days = sorted(rng.choice(days_in_quarter, size=n_nps, replace=False))
            nps_samples = np.round(np.clip(rng.uniform(20, 68) + rng.normal(0, 6, n_nps), 0, 100), 1)
            for d, score in zip(nps_days, nps_samples):
                reading_date = quarter_start + timedelta(days=int(d))
                reading_rows.append({
                    "Region": region, "Quarter": q, "Date": reading_date.isoformat(),
                    "Reading Type": "NPS Survey",
                    "Revenue Amount": np.nan, "NPS Score": float(score), "CSAT Score": np.nan,
                })
            # Derived from the *stored* (already-rounded) sample values, not the raw draws, so
            # the report figure reconciles exactly against the origin CSV a consumer would read.
            nps_value = int(round(float(np.mean(nps_samples))))

            n_csat = int(rng.integers(6, 12))
            csat_days = sorted(rng.choice(days_in_quarter, size=n_csat, replace=False))
            csat_samples = np.round(np.clip(rng.uniform(78, 96) + rng.normal(0, 2.5, n_csat), 0, 100), 1)
            for d, score in zip(csat_days, csat_samples):
                reading_date = quarter_start + timedelta(days=int(d))
                reading_rows.append({
                    "Region": region, "Quarter": q, "Date": reading_date.isoformat(),
                    "Reading Type": "CSAT Survey",
                    "Revenue Amount": np.nan, "NPS Score": np.nan, "CSAT Score": float(score),
                })
            csat_value = round(float(np.mean(csat_samples)), 1)

            if prev_revenue is None:
                growth = round(rng.normal(6, 4), 1)
            else:
                growth = round((quarter_revenue / prev_revenue - 1) * 100, 1)
            prev_revenue = quarter_revenue

            churn = round(rng.uniform(1.0, 6.5), 1)
            cac = round(rng.uniform(400, 2200), 0)
            ltv = round(cac * rng.uniform(2.5, 6.0), 0)

            report_rows.append({
                "Region": region,
                "Quarter": q,
                "Revenue": quarter_revenue,
                "Revenue Growth %": growth,
                "NPS": nps_value,
                "Churn %": churn,
                "CAC": cac,
                "LTV": ltv,
                "CSAT %": csat_value,
            })

    origin_df = pd.DataFrame(reading_rows)
    df = pd.DataFrame(report_rows)

    # Noise columns — realistic-looking but analytically inert.
    reading_types = origin_df["Reading Type"].tolist()
    origin_df = add_noise_columns(origin_df, rng, fake, {
        "Reading ID": sequential_id("KPI", 900000),
        "Survey Respondent": lambda r, f, i: f.name() if reading_types[i] != "Daily Revenue" else "",
        "Data Source System": lambda r, f, i: r.choice(DATA_SOURCES),
    })
    origin_df = origin_df[[
        "Reading ID", "Region", "Quarter", "Date", "Reading Type",
        "Revenue Amount", "NPS Score", "CSAT Score", "Survey Respondent", "Data Source System",
    ]]

    latest_q = QUARTERS[-1]
    latest = df[df["Quarter"] == latest_q].drop(columns=["Quarter"]).reset_index(drop=True)

    detail_table = dataframe_to_table(
        df, f"Table 2. KPI Detail by Region and Quarter, {fy}",
        currency_cols=("Revenue", "CAC", "LTV"),
        percent_cols=("Revenue Growth %", "Churn %", "CSAT %"),
        int_cols=("NPS",), total_row=False,
    )
    latest_table = dataframe_to_table(
        latest, f"Table 1. Regional KPI Snapshot — {latest_q} {fy}",
        currency_cols=("Revenue", "CAC", "LTV"),
        percent_cols=("Revenue Growth %", "Churn %", "CSAT %"),
        int_cols=("NPS",), total_row=False,
    )

    best_growth = latest.sort_values("Revenue Growth %", ascending=False).iloc[0]
    best_ltv_cac = latest.assign(ratio=latest["LTV"] / latest["CAC"]).sort_values("ratio", ascending=False).iloc[0]
    summary_text = generate_summary(
        f"{TITLE} — {fy}",
        f"Snapshot for {latest_q} {fy} across regions {', '.join(REGIONS)}. "
        f"Highest revenue growth: {best_growth['Region']} ({best_growth['Revenue Growth %']:.1f}%). "
        f"Best LTV:CAC ratio: {best_ltv_cac['Region']} ({best_ltv_cac['LTV']/best_ltv_cac['CAC']:.1f}x).",
        fallback=(
            "This scorecard tracks key performance indicators — revenue, growth, customer "
            "satisfaction, and unit economics — across all operating regions. North America and "
            "EMEA continue to lead on LTV:CAC ratio, while APAC shows the strongest revenue growth "
            f"rate of any region this fiscal year ({fy})."
        ),
    )

    context = base_context(f"{TITLE} — {fy}", year)
    context["kpi_tiles"] = [
        {"label": "Fastest Growth", "value": best_growth["Region"]},
        {"label": "Best LTV:CAC", "value": best_ltv_cac["Region"]},
        {"label": "Regions Tracked", "value": str(len(REGIONS))},
    ]
    context["sections"] = [
        {
            "heading": "Executive Summary",
            "narrative": [summary_text],
            "tables": [latest_table],
        },
        {
            "heading": "Quarterly KPI Detail",
            "narrative": [],
            "tables": [detail_table],
        },
    ]
    context["footnotes"] = [
        "NPS: Net Promoter Score. CSAT: Customer Satisfaction Score. CAC: Customer Acquisition Cost. LTV: Customer Lifetime Value.",
        "All monetary figures are presented in USD thousands unless otherwise noted.",
    ]

    render_pdf(DEPARTMENT, context, output_dir / "raw" / f"10_regional_kpi_scorecard{suffix}.pdf")
    write_ground_truth(
        output_dir / "golden" / f"10_regional_kpi_scorecard{suffix}.json",
        {"detail": df, "latest_quarter": latest},
        report_id=REPORT_ID,
        report_title=TITLE,
        department=DEPARTMENT,
        year=year,
    )
    write_origin_csv(origin_df, output_dir / "origin" / f"10_regional_kpi_scorecard{suffix}.csv")
