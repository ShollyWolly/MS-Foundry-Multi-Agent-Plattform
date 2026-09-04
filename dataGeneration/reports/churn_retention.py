"""Customer Churn & Retention Report — cohort retention by segment over 12 months."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from lib.common import base_context, make_faker
from lib.fiscal import fy_label, fy_year_start
from lib.groundtruth import write_ground_truth, write_origin_csv
from lib.narrative import generate_summary
from lib.noise import add_noise_columns
from lib.render import render_pdf
from lib.tables import dataframe_to_table

SEED = 6
DEPARTMENT = "customer_success"
REPORT_ID = "customer_churn_retention"
TITLE = "Customer Churn & Retention Report"
SEGMENTS = ["Enterprise", "Mid-Market", "SMB"]
SIGNUP_CHANNELS = ["Inbound Sales", "Self-Serve", "Partner Referral", "Outbound Sales", "Marketing Campaign"]


def generate(output_dir: Path, year: int) -> None:
    rng = np.random.default_rng(SEED + year)
    fake = make_faker(SEED + year)
    fy = fy_label(year)
    suffix = f"_{fy}"

    year_start = fy_year_start(year)
    months = pd.period_range(start=year_start.strftime("%Y-%m"), periods=12, freq="M")

    # Step 1: individual customer subscription lifecycle events (signup/churn) per segment,
    # generated month by month so the active pool per segment evolves realistically — the
    # monthly cohort counts (Starting/New/Churned/Ending) are then derived FROM these events,
    # not generated independently.
    base_churn = {"Enterprise": 0.8, "Mid-Market": 2.2, "SMB": 4.5}
    starting = {"Enterprise": 220, "Mid-Market": 640, "SMB": 1800}

    active_pool: dict[str, set[str]] = {seg: set() for seg in SEGMENTS}
    customer_names: dict[str, str] = {}
    next_customer_num = [100000]

    def new_customer_id() -> str:
        cid = f"CUST-{next_customer_num[0]}"
        next_customer_num[0] += 1
        return cid

    # Seed the initial active pool (pre-existing customers at the start of the fiscal year —
    # they have no signup event within this year's origin data).
    for seg in SEGMENTS:
        for _ in range(starting[seg]):
            cid = new_customer_id()
            active_pool[seg].add(cid)
            customer_names[cid] = fake.company()

    origin_rows = []
    for month in months:
        month_start = month.to_timestamp()
        days_in_month = month.days_in_month
        for seg in SEGMENTS:
            starting_count = len(active_pool[seg])
            churn_rate = max(0.1, base_churn[seg] + rng.normal(0, 0.6))
            churned_n = min(int(round(starting_count * churn_rate / 100)), starting_count)
            new_n = int(rng.integers(5, 60)) if seg != "Enterprise" else int(rng.integers(1, 10))

            churn_targets = rng.choice(sorted(active_pool[seg]), size=churned_n, replace=False) if churned_n > 0 else []
            for cid in churn_targets:
                event_date = month_start + pd.Timedelta(days=int(rng.integers(0, days_in_month)))
                origin_rows.append({
                    "Customer ID": cid,
                    "Customer Name": customer_names[cid],
                    "Segment": seg,
                    "Event Type": "Churn",
                    "Event Date": event_date.date().isoformat(),
                })
                active_pool[seg].discard(cid)

            for _ in range(new_n):
                cid = new_customer_id()
                customer_names[cid] = fake.company()
                active_pool[seg].add(cid)
                event_date = month_start + pd.Timedelta(days=int(rng.integers(0, days_in_month)))
                origin_rows.append({
                    "Customer ID": cid,
                    "Customer Name": customer_names[cid],
                    "Segment": seg,
                    "Event Type": "Signup",
                    "Event Date": event_date.date().isoformat(),
                })

    origin_df = pd.DataFrame(origin_rows)
    origin_df["Month"] = pd.to_datetime(origin_df["Event Date"]).dt.to_period("M").astype(str)

    # Step 2: noise columns — realistic-looking but analytically inert.
    event_types = origin_df["Event Type"].tolist()
    origin_df = add_noise_columns(origin_df, rng, fake, {
        "Signup Channel": lambda r, f, i: r.choice(SIGNUP_CHANNELS),
        "Cancellation Reason": lambda r, f, i: f.bs() if event_types[i] == "Churn" else "",
    })
    origin_df = origin_df[[
        "Customer ID", "Customer Name", "Segment", "Event Type", "Event Date", "Month",
        "Signup Channel", "Cancellation Reason",
    ]]

    # Step 3: derive the report's monthly cohort table FROM the origin events via groupby/count,
    # then reconstruct Starting/Ending counts with the same recurrence used to generate the pool.
    counts = origin_df.groupby(["Month", "Segment", "Event Type"]).size().unstack(fill_value=0)
    for col in ("Signup", "Churn"):
        if col not in counts.columns:
            counts[col] = 0

    running = dict(starting)
    cohort_rows = []
    for month in months:
        month_key = str(month)
        for seg in SEGMENTS:
            new_n = int(counts.loc[(month_key, seg), "Signup"]) if (month_key, seg) in counts.index else 0
            churned_n = int(counts.loc[(month_key, seg), "Churn"]) if (month_key, seg) in counts.index else 0
            starting_count = running[seg]
            ending_count = starting_count - churned_n + new_n
            running[seg] = ending_count
            churn_rate_pct = round(churned_n / starting_count * 100, 2) if starting_count else 0.0
            cohort_rows.append({
                "Month": month_key,
                "Segment": seg,
                "Starting Customers": starting_count,
                "New Customers": new_n,
                "Churned": churned_n,
                "Ending Customers": ending_count,
                "Churn Rate %": churn_rate_pct,
            })
    df = pd.DataFrame(cohort_rows)

    latest_month = str(months[-1])
    latest = df[df["Month"] == latest_month][["Segment", "Ending Customers", "Churn Rate %"]].reset_index(drop=True)
    latest_label = months[-1].strftime("%b %Y")

    detail_table = dataframe_to_table(
        df, f"Table 2. Monthly Cohort Detail by Segment ({fy})",
        int_cols=("Starting Customers", "New Customers", "Churned", "Ending Customers"),
        percent_cols=("Churn Rate %",),
        total_row=False,
    )
    summary_table = dataframe_to_table(
        latest, f"Table 1. Current Customer Base and Churn Rate by Segment ({latest_label})",
        int_cols=("Ending Customers",), percent_cols=("Churn Rate %",), total_row=False,
    )

    summary_rows = {r["Segment"]: r for r in latest.to_dict(orient="records")}
    summary_text = generate_summary(
        f"{TITLE} — {fy}",
        f"Current customer base and monthly churn rate by segment ({latest_label}): "
        + "; ".join(f"{seg}: {r['Ending Customers']} customers, {r['Churn Rate %']:.1f}% churn" for seg, r in summary_rows.items())
        + f". Segments covered: {', '.join(SEGMENTS)}.",
        fallback=(
            "Enterprise churn remains low and stable, while SMB churn is elevated relative to target, "
            "consistent with typical patterns for lower-touch segments. Net customer growth remains "
            f"positive across all segments over {fy}."
        ),
    )

    total_customers = int(latest["Ending Customers"].sum())
    context = base_context(f"{TITLE} — {fy}", year)
    context["kpi_tiles"] = [
        {"label": "Active Customers", "value": f"{total_customers:,}"},
        {"label": "Segments", "value": str(len(SEGMENTS))},
        {"label": "Months Tracked", "value": str(len(months))},
    ]
    context["sections"] = [
        {
            "heading": "Executive Summary",
            "narrative": [summary_text],
            "tables": [summary_table],
        },
        {
            "heading": "Monthly Cohort Detail",
            "narrative": [],
            "tables": [detail_table],
        },
    ]
    context["footnotes"] = [
        "Churn Rate % is calculated as customers churned in the month divided by starting customers.",
        "Segment definitions: Enterprise (>1,000 seats), Mid-Market (50-1,000 seats), SMB (<50 seats).",
    ]

    render_pdf(DEPARTMENT, context, output_dir / "raw" / f"06_customer_churn_retention{suffix}.pdf")
    write_ground_truth(
        output_dir / "golden" / f"06_customer_churn_retention{suffix}.json",
        {"detail": df, "current_summary": latest},
        report_id=REPORT_ID,
        report_title=TITLE,
        department=DEPARTMENT,
        year=year,
    )
    write_origin_csv(origin_df, output_dir / "origin" / f"06_customer_churn_retention{suffix}.csv")
