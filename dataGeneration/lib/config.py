"""Loads dataGeneration/config.yaml once and exposes it as a simple attribute-free dict-like
object. Edit config.yaml to change generation behavior — no Python changes needed for the
settings it exposes.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


@lru_cache(maxsize=1)
def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def company_config() -> dict:
    return load_config()["company"]


def generation_config() -> dict:
    return load_config()["generation"]
