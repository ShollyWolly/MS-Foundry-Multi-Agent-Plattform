"""Fiscal-year label helpers shared by every report generator, so year strings are derived from
a single `year: int` parameter (itself sourced from config.yaml's generation.years) instead of
being hardcoded per-module. This codebase treats fiscal year == calendar year (Jan 1 - Dec 31).
"""
from __future__ import annotations

from datetime import date


def fy_label(year: int) -> str:
    """e.g. fy_label(2025) -> "FY2025"."""
    return f"FY{year}"


def fy_quarter_label(year: int, quarter_index: int) -> str:
    """quarter_index is 0-3. e.g. fy_quarter_label(2026, 0) -> "Q1 FY2026"."""
    return f"Q{quarter_index + 1} {fy_label(year)}"


def fy_year_start(year: int) -> date:
    return date(year, 1, 1)


def report_prepared_date(year: int) -> str:
    """The cover-page 'prepared on' date — reports are prepared shortly after their fiscal year
    closes, so this is Q1 of the *following* calendar year (e.g. year=2020 -> "March 31, 2021"),
    not a fixed date reused across every fiscal year."""
    return f"March 31, {year + 1}"


def trailing_fy_labels(year: int, n: int = 3) -> list[str]:
    """e.g. trailing_fy_labels(2025, 3) -> ["FY2023", "FY2024", "FY2025"] — anchors a trailing
    multi-year trend view on whichever year is currently being generated."""
    return [fy_label(year - (n - 1) + i) for i in range(n)]
