"""Validation plan Step 3 & 4 — table extraction on hard documents.

Converts each document in samples/ that's expected to contain tables and
exports every detected table to both HTML (for human review of merged
cells/spans) and CSV (for programmatic spot-checking), per
EXTRACTION_APPROACH.md Section 3's output-format decision.

Usage: python 03_table_extraction.py <path-to-doc-1> [<path-to-doc-2> ...]
If no paths given, runs against every file in samples/.
"""

import sys
from pathlib import Path

from common import build_converter, report_writer

SAMPLES_DIR = Path(__file__).parent / "samples"
OUTPUT_DIR = Path(__file__).parent / "output" / "tables"


def main():
    doc_paths = [Path(p) for p in sys.argv[1:]] or [
        f for f in SAMPLES_DIR.iterdir() if f.is_file()
    ]

    if not doc_paths:
        print(f"No documents found. Drop files in {SAMPLES_DIR} or pass paths as args.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    converter = build_converter()

    with report_writer("03_table_extraction") as (emit, report_path):
        for doc_path in doc_paths:
            result = converter.convert(doc_path)
            doc = result.document

            if not doc.tables:
                emit(f"{doc_path.name}: no tables detected")
                continue

            emit(f"{doc_path.name}: {len(doc.tables)} table(s) detected")
            for i, table in enumerate(doc.tables):
                stem = doc_path.stem
                html_path = OUTPUT_DIR / f"{stem}-table-{i}.html"
                csv_path = OUTPUT_DIR / f"{stem}-table-{i}.csv"

                html_path.write_text(table.export_to_html(doc=doc), encoding="utf-8")

                df = table.export_to_dataframe(doc=doc)
                df.to_csv(csv_path, index=False)

                emit(f"  Table {i}: {df.shape[0]}x{df.shape[1]} -> {html_path.name}, {csv_path.name}")

        emit(f"\nOutputs written to {OUTPUT_DIR}")
        emit("Next: manually diff each HTML output against the source document page image")
        emit("(cell merges, header association, row/column order) per validation plan Step 4.")

    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    main()
