"""Adds realistic-looking but analytically-inert extra columns ("noise") to an origin-level
DataFrame — record IDs, timestamps, people/company names, free text, etc. These columns exist so
the origin CSVs look like plausible raw operational exports, without influencing any aggregate
figure the report/golden JSON derives from the DataFrame's "real" columns.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd
from faker import Faker

# new_column_name -> a callable taking (rng, fake, row_index) and returning a scalar. Called once
# per row, in insertion order. Generators are independent of each other by design (no column can
# reference another noise column's value) — keeps each one easy to reason about / swap out.
NoiseSpec = dict[str, Callable[[np.random.Generator, Faker, int], object]]


def add_noise_columns(df: pd.DataFrame, rng: np.random.Generator, fake: Faker, spec: NoiseSpec) -> pd.DataFrame:
    df = df.copy()
    n = len(df)
    for col_name, gen in spec.items():
        df[col_name] = [gen(rng, fake, i) for i in range(n)]
    return df


def sequential_id(prefix: str, start: int = 100000) -> Callable:
    def _gen(rng, fake, i):
        return f"{prefix}-{start + i}"

    return _gen


def random_timestamp_in(year: int) -> Callable:
    def _gen(rng, fake, i):
        return fake.date_time_between(start_date=f"{year}-01-01", end_date=f"{year}-12-31")

    return _gen
