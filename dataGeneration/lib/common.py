"""Shared constants/helpers used across report generators. Company identity comes from
config.yaml (see lib/config.py) so it's editable without touching Python code."""
from __future__ import annotations

from faker import Faker

from .config import company_config
from .fiscal import report_prepared_date

_company = company_config()
COMPANY_NAME = _company["name"]
PREPARED_BY = _company["prepared_by"]
# Fallback only, for any call site that doesn't pass a fiscal year — every report module should
# pass `year` to base_context() so the cover-page date tracks the fiscal year being reported
# (see lib/fiscal.py::report_prepared_date), not this fixed config.yaml value.
REPORT_DATE = _company["report_date"]

# Grounds LLM-generated narrative text (see lib/narrative.py) in a consistent company/business
# context, so summaries make sense as part of a coherent set of documents rather than reading
# like generic, interchangeable corporate filler.
COMPANY_DESCRIPTION = _company["description"].strip()

REGIONS = ["North America", "EMEA", "APAC", "LATAM"]
QUARTERS = ["Q1", "Q2", "Q3", "Q4"]
DEPARTMENTS = [
    "Sales", "Marketing", "Engineering", "Product", "Customer Success",
    "Finance", "Human Resources", "Operations", "Legal", "IT",
]


def make_faker(seed: int) -> Faker:
    fake = Faker()
    Faker.seed(seed)
    return fake


def base_context(title: str, year: int | None = None) -> dict:
    return {
        "title": title,
        "company_name": COMPANY_NAME,
        "report_date": report_prepared_date(year) if year is not None else REPORT_DATE,
        "prepared_by": PREPARED_BY,
    }
