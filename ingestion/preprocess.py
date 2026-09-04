#!/usr/bin/env python3
"""Pre-processes the report PDFs (dataGeneration/output/raw/) for the Search indexer/skillset
pipeline: extract (Content Understanding) -> filter -> group into section/table sidecar blobs ->
upload to ADLS Gen2, with blob metadata carrying report identity. Chunking beyond this (narrative
sub-splitting, embeddings) happens inside the indexer's skillset (see setup_indexer.py), not
here — this script's job ends at "correctly-scoped, metadata-tagged text sits in blob storage."

Run with the `rag-ingestion` conda env active:

    conda activate rag-ingestion
    python ingestion/preprocess.py [year]

Safe to re-run: blobs are named deterministically from (report_id, year, section/table index),
so re-running after a chunking/extraction change overwrites existing blobs in place. Deleting a
PDF from a previous run's set does NOT automatically remove its blobs — see CLAUDE.md's note on
this pipeline's deletion-detection story (it protects against a *deleted* source blob, not
against source PDFs that stopped being generated).
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.chunk import chunk_table  # noqa: E402
from lib.config import load_config  # noqa: E402
from lib.extract import extract_pdf, group_into_sections  # noqa: E402
from lib.filter import filter_document  # noqa: E402
from lib.retry import retry_with_backoff  # noqa: E402
from lib.azure_clients import blob_service_client  # noqa: E402

_SUFFIX_RE = re.compile(r"_FY(\d{4})$")


def _report_identity(pdf_path: Path, golden_dir: Path, default_year: int) -> dict:
    """Reads report_id/report_title/department/year from the sibling golden JSON dataGeneration
    writes next to every PDF. Falls back to filename parsing only if the golden JSON is missing
    (e.g. an older output tree) — this is a data contract with dataGeneration, not an import."""
    golden_path = golden_dir / f"{pdf_path.stem}.json"
    if golden_path.exists():
        data = json.loads(golden_path.read_text())
        if "report_id" in data:
            return {
                "report_id": data["report_id"],
                "report_title": data["report_title"],
                "department": data["department"],
                "year": data["year"],
            }
    m = _SUFFIX_RE.search(pdf_path.stem)
    year = int(m.group(1)) if m else default_year
    stem = _SUFFIX_RE.sub("", pdf_path.stem)
    report_id = re.sub(r"^\d+_", "", stem)
    return {"report_id": report_id, "report_title": report_id.replace("_", " ").title(), "department": "", "year": year}


def _upload_text(container_client, blob_name: str, text: str, metadata: dict) -> None:
    str_metadata = {k: str(v) for k, v in metadata.items()}
    container_client.upload_blob(name=blob_name, data=text.encode("utf-8"), overwrite=True, metadata=str_metadata)


def process_pdf(pdf_path: Path, golden_dir: Path, config: dict, raw_container, sections_container) -> tuple[int, int]:
    identity = _report_identity(pdf_path, golden_dir, config["default_year"])
    report_id, year = identity["report_id"], identity["year"]
    identity["report_key"] = f"{report_id}:{year}"
    identity["source_pdf_url"] = raw_container.get_blob_client(f"{year}/{report_id}.pdf").url

    doc = retry_with_backoff(lambda: extract_pdf(pdf_path), label=f"extract:{pdf_path.name}")
    doc = filter_document(doc)
    sections = group_into_sections(doc.paragraphs)

    summary_heading = config["summary_heading"].strip().lower()
    n_sections = 0
    for i, section in enumerate(sections):
        chunk_type = "summary" if section.heading.strip().lower() == summary_heading else "narrative"
        metadata = {
            **identity,
            "chunk_type": chunk_type,
            "section_heading": section.heading,
            "page_number": section.page_number or 0,
        }
        blob_name = f"sections/{year}/{report_id}/section-{i}.txt"
        _upload_text(sections_container, blob_name, section.text, metadata)
        n_sections += 1

    n_tables = 0
    for t_idx, table in enumerate(doc.tables):
        table_chunks = chunk_table(table, config["chunking"]["table_max_tokens"])
        for c_idx, chunk in enumerate(table_chunks):
            metadata = {
                **identity,
                "chunk_type": "table",
                "section_heading": chunk.caption,
                "page_number": chunk.page_number or 0,
            }
            blob_name = f"tables/{year}/{report_id}/table-{t_idx}-{c_idx}.txt"
            _upload_text(sections_container, blob_name, chunk.content, metadata)
            n_tables += 1

    # Raw PDF, for citation links from index documents back to the source document.
    with open(pdf_path, "rb") as f:
        raw_container.upload_blob(name=f"{year}/{report_id}.pdf", data=f, overwrite=True)

    return n_sections, n_tables


def main() -> int:
    config = load_config()
    input_dir = (Path(__file__).resolve().parent / config["input_dir"]).resolve()
    golden_dir = input_dir.parent / "golden"

    pdf_paths = sorted(input_dir.glob("*.pdf"))
    if not pdf_paths:
        print(f"error: no PDFs found in {input_dir}", file=sys.stderr)
        return 1

    service = blob_service_client()
    raw_container = service.get_container_client(config["raw_container"])
    sections_container = service.get_container_client(config["sections_container"])

    for pdf_path in pdf_paths:
        start = time.time()
        n_sections, n_tables = process_pdf(pdf_path, golden_dir, config, raw_container, sections_container)
        print(f"  {pdf_path.name}: {n_sections} section blobs, {n_tables} table-chunk blobs ({time.time() - start:.1f}s)")

    print(f"\nDone. Uploaded blobs for {len(pdf_paths)} PDFs to '{config['raw_container']}' / '{config['sections_container']}'.")
    print("Run ingestion/setup_indexer.py next (first time / after a schema change), then trigger the indexers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
