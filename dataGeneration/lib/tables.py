"""Converts a pandas DataFrame into the row/column structure the generic report template
expects, applying per-column display formatting and an optional computed Total row.
"""
from __future__ import annotations

import pandas as pd

from .style import fmt_currency, fmt_percent, fmt_thousands


def dataframe_to_table(
    df: pd.DataFrame,
    caption: str,
    currency_cols: tuple[str, ...] = (),
    percent_cols: tuple[str, ...] = (),
    int_cols: tuple[str, ...] = (),
    header_groups: list[dict] | None = None,
    total_row: bool = True,
    total_label: str = "Total",
) -> dict:
    columns = list(df.columns)

    def fmt_cell(col: str, value) -> str:
        if col in currency_cols:
            return fmt_currency(value)
        if col in percent_cols:
            return fmt_percent(value)
        if col in int_cols:
            return fmt_thousands(value)
        return str(value)

    rows = []
    for _, r in df.iterrows():
        rows.append({"cells": [fmt_cell(c, r[c]) for c in columns], "class": ""})

    if total_row:
        cells = []
        for i, c in enumerate(columns):
            if i == 0:
                cells.append(total_label)
            elif c in currency_cols:
                cells.append(fmt_currency(df[c].sum()))
            elif c in int_cols:
                cells.append(fmt_thousands(df[c].sum()))
            else:
                cells.append("")
        rows.append({"cells": cells, "class": "total"})

    return {
        "caption": caption,
        "header_groups": header_groups or [],
        "columns": columns,
        "rows": rows,
    }
