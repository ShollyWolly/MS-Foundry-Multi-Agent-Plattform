"""Inventory & Supply Chain Report — stock levels by SKU and warehouse."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from lib.common import base_context, make_faker
from lib.fiscal import fy_year_start
from lib.groundtruth import write_ground_truth, write_origin_csv
from lib.narrative import generate_summary
from lib.noise import add_noise_columns, sequential_id
from lib.render import render_pdf
from lib.tables import dataframe_to_table

SEED = 4
DEPARTMENT = "operations"
REPORT_ID = "inventory_supply_chain_report"
TITLE = "Inventory & Supply Chain Report"
WAREHOUSES = ["Portland, OR", "Columbus, OH", "Rotterdam, NL", "Kuala Lumpur, MY", "Monterrey, MX"]
CATEGORIES = ["Servers", "Networking", "Storage", "Peripherals", "Cabling", "Power & Cooling"]


def generate(output_dir: Path, year: int) -> None:
    rng = np.random.default_rng(SEED + year)
    fake = make_faker(SEED + year)
    year_start = fy_year_start(year)
    year_end = year_start.replace(month=12, day=31)
    as_of_month_label = year_start.replace(month=3).strftime("%B %Y")  # keep the "March <year>" framing
    suffix = f"_FY{year}"

    # Step 1: coarse per-SKU targets (same shape as before) — these now act as targets the
    # origin-level movement ledger must net out to exactly, not final numbers.
    sku_targets = []
    for i in range(70):
        category = CATEGORIES[i % len(CATEGORIES)]
        on_hand = int(rng.integers(0, 2000))
        reorder_point = int(rng.integers(50, 400))
        monthly_usage = int(rng.integers(20, 600))
        annual_usage = monthly_usage * 12
        sku_targets.append({
            "SKU": f"SKU-{1000 + i}",
            "Category": category,
            "Warehouse": rng.choice(WAREHOUSES),
            "On Hand": on_hand,
            "Reorder Point": reorder_point,
            "Monthly Usage": monthly_usage,
            "Annual Usage": annual_usage,
        })

    # Step 2: explode each SKU's target into individual receipt/shipment/adjustment movement
    # events across the fiscal year. Shipments are constructed to sum exactly to the SKU's
    # annual usage target; a single opening receipt plus a small number of restock receipts are
    # constructed so that opening_receipts + restocks - shipments == the SKU's ending on-hand
    # target (guaranteeing the origin ledger nets back to today's report numbers by construction).
    origin_rows = []
    for sku in sku_targets:
        # Shipments: split annual usage across n_ship events via a Dirichlet split.
        n_ship = int(rng.integers(6, 24))
        ship_weights = rng.dirichlet(np.ones(n_ship))
        ship_qtys = np.round(ship_weights * sku["Annual Usage"]).astype(int)
        ship_qtys[-1] += sku["Annual Usage"] - ship_qtys.sum()  # fix rounding residual
        ship_qtys = np.clip(ship_qtys, 0, None)

        total_shipped = int(ship_qtys.sum())
        # Receipts must net to: ending_on_hand + total_shipped (plus/minus a small adjustment).
        adjustment_qty = int(rng.integers(-15, 16))
        total_receipts_needed = sku["On Hand"] + total_shipped - adjustment_qty
        total_receipts_needed = max(total_receipts_needed, 0)

        n_receipt = int(rng.integers(2, 6))
        if total_receipts_needed > 0:
            receipt_weights = rng.dirichlet(np.ones(n_receipt))
            receipt_qtys = np.round(receipt_weights * total_receipts_needed).astype(int)
            receipt_qtys[-1] += total_receipts_needed - receipt_qtys.sum()
            receipt_qtys = np.clip(receipt_qtys, 0, None)
        else:
            receipt_qtys = np.zeros(n_receipt, dtype=int)

        # Recompute the actual adjustment as whatever residual makes the ledger net exactly to
        # the target on-hand (keeps the identity exact even after the int-rounding above).
        actual_adjustment = sku["On Hand"] - (int(receipt_qtys.sum()) - total_shipped)

        for qty in receipt_qtys:
            event_date = year_start + timedelta(days=int(rng.integers(0, 365)))
            origin_rows.append({
                "SKU": sku["SKU"], "Category": sku["Category"], "Warehouse": sku["Warehouse"],
                "Event Date": event_date.isoformat(), "Transaction Type": "Receipt",
                "Quantity": int(qty),
            })
        for qty in ship_qtys:
            event_date = year_start + timedelta(days=int(rng.integers(0, 365)))
            origin_rows.append({
                "SKU": sku["SKU"], "Category": sku["Category"], "Warehouse": sku["Warehouse"],
                "Event Date": event_date.isoformat(), "Transaction Type": "Shipment",
                "Quantity": -int(qty),
            })
        if actual_adjustment != 0:
            event_date = year_start + timedelta(days=int(rng.integers(0, 365)))
            origin_rows.append({
                "SKU": sku["SKU"], "Category": sku["Category"], "Warehouse": sku["Warehouse"],
                "Event Date": event_date.isoformat(), "Transaction Type": "Adjustment",
                "Quantity": int(actual_adjustment),
            })

    origin_df = pd.DataFrame(origin_rows).sort_values(["SKU", "Event Date"]).reset_index(drop=True)

    # Step 3: noise columns — realistic-looking but analytically inert.
    origin_df = add_noise_columns(origin_df, rng, fake, {
        "Transaction ID": sequential_id("INV", 800000),
        "Warehouse Clerk": lambda r, f, i: f.name(),
        "Notes": lambda r, f, i: f.bs().capitalize(),
    })
    origin_df = origin_df[[
        "Transaction ID", "SKU", "Category", "Warehouse", "Event Date", "Transaction Type",
        "Quantity", "Warehouse Clerk", "Notes",
    ]]

    # Step 4: derive the report's tables FROM the origin movement ledger (not independently
    # generated) — On Hand nets receipts + adjustments + shipments (shipments already negative).
    reorder_points = {s["SKU"]: s["Reorder Point"] for s in sku_targets}
    monthly_usage_targets = {s["SKU"]: s["Monthly Usage"] for s in sku_targets}

    net_by_sku = origin_df.groupby("SKU", as_index=False)["Quantity"].sum().rename(columns={"Quantity": "On Hand"})
    shipped_by_sku = (
        origin_df[origin_df["Transaction Type"] == "Shipment"]
        .groupby("SKU", as_index=False)["Quantity"].sum()
        .rename(columns={"Quantity": "Total Shipped"})
    )
    shipped_by_sku["Total Shipped"] = -shipped_by_sku["Total Shipped"]

    meta = origin_df.drop_duplicates("SKU")[["SKU", "Category", "Warehouse"]]
    df = meta.merge(net_by_sku, on="SKU").merge(shipped_by_sku, on="SKU")
    df["Reorder Point"] = df["SKU"].map(reorder_points)
    df["Monthly Usage"] = (df["Total Shipped"] / 12).round().astype(int)
    df["Months of Supply"] = (df["On Hand"] / df["Monthly Usage"].clip(lower=1)).round(1)
    df["Status"] = np.where(df["On Hand"] < df["Reorder Point"], "Reorder Needed", "OK")
    df = df[["SKU", "Category", "Warehouse", "On Hand", "Reorder Point", "Monthly Usage",
             "Months of Supply", "Status"]]

    by_category = df.groupby("Category", as_index=False)[["On Hand", "Monthly Usage"]].sum()
    low_stock_count = int((df["Status"] == "Reorder Needed").sum())

    detail_table = dataframe_to_table(
        df, "Table 2. Inventory Detail by SKU",
        int_cols=("On Hand", "Reorder Point", "Monthly Usage"),
        total_row=False,
    )
    category_table = dataframe_to_table(
        by_category, "Table 1. Inventory Summary by Category",
        int_cols=("On Hand", "Monthly Usage"),
    )

    top_category = by_category.sort_values("On Hand", ascending=False).iloc[0]
    summary_text = generate_summary(
        f"Inventory & Supply Chain Report — {as_of_month_label}",
        f"{low_stock_count} of {len(df)} SKUs are below their reorder point and need replenishment. "
        f"Category with highest on-hand inventory: {top_category['Category']} ({int(top_category['On Hand'])} units). "
        f"Warehouses covered: {', '.join(WAREHOUSES)}.",
        fallback=(
            f"As of {as_of_month_label}, {low_stock_count} SKUs across the network are below their reorder "
            "point and require replenishment action. Storage and Networking categories carry the "
            "highest on-hand balances relative to monthly usage."
        ),
    )

    context = base_context(f"Inventory & Supply Chain Report — {as_of_month_label}", year)
    context["sections"] = [
        {
            "heading": "Executive Summary",
            "narrative": [summary_text],
            "tables": [category_table],
        },
        {
            "heading": "SKU-Level Inventory Detail",
            "narrative": [
                "SKUs flagged \"Reorder Needed\" have fallen below their configured reorder point based "
                "on current on-hand quantity.",
            ],
            "tables": [detail_table],
        },
    ]
    context["footnotes"] = [
        "Months of Supply is calculated as On Hand divided by trailing Monthly Usage.",
        f"Warehouse locations: {', '.join(WAREHOUSES)}.",
    ]

    render_pdf(DEPARTMENT, context, output_dir / "raw" / f"04_inventory_supply_chain{suffix}.pdf")
    write_ground_truth(
        output_dir / "golden" / f"04_inventory_supply_chain{suffix}.json",
        {"detail": df, "by_category": by_category},
        {"low_stock_sku_count": low_stock_count},
        report_id=REPORT_ID,
        report_title=TITLE,
        department=DEPARTMENT,
        year=year,
    )
    write_origin_csv(origin_df, output_dir / "origin" / f"04_inventory_supply_chain{suffix}.csv")
