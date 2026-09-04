#!/usr/bin/env python3
"""Generates the synthetic BI report PDFs (+ ground-truth JSON sidecars) used as example RAG
data. What gets generated is controlled by config.yaml — see that file to change the company
identity, which reports run, the output directory, or disable LLM narrative generation. Run with
the `rag-data-generator` conda env active:

    conda activate rag-data-generator
    python dataGeneration/generate_reports.py

Output lands in dataGeneration/output/ (or config.yaml's generation.output_dir) — gitignored,
regenerate rather than committing.
"""
import importlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.config import generation_config  # noqa: E402


def main() -> int:
    config = generation_config()
    output_dir = Path(__file__).resolve().parent / config.get("output_dir", "output")
    output_dir.mkdir(parents=True, exist_ok=True)

    report_ids = config["reports"]
    years = config.get("years", [2025])
    total = 0
    for year in years:
        for report_id in report_ids:
            module = importlib.import_module(f"reports.{report_id}")
            start = time.time()
            module.generate(output_dir, year)
            print(f"  generated {report_id} {year} ({time.time() - start:.1f}s)")
            total += 1

    print(f"\nDone. {total} report/year sets written to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
