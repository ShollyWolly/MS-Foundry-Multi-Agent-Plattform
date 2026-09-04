"""Small retry-with-backoff helper — the same RBAC-propagation-lag pattern hit repeatedly
elsewhere in this project (infra/scripts/create_agent.py, dataGeneration/lib/llm.py): a role
assignment can take several minutes to actually take effect after `terraform apply`.
"""
from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def retry_with_backoff(fn: Callable[[], T], attempts: int = 10, delay_seconds: int = 15, label: str = "operation") -> T:
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            if attempt == attempts:
                raise
            print(
                f"  [{label}] attempt {attempt}/{attempts} failed ({exc}); retrying in {delay_seconds}s "
                "(likely waiting on RBAC role propagation)"
            )
            time.sleep(delay_seconds)
    raise RuntimeError("unreachable")  # pragma: no cover
