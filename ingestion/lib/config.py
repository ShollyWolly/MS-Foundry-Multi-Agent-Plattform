"""Loads ingestion/config.yaml once. Mirrors dataGeneration/lib/config.py's pattern, but kept as
a separate implementation on purpose — this is a decoupled part of the project."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


@lru_cache(maxsize=1)
def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
