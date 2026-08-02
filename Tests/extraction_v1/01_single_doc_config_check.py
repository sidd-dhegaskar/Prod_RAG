"""Validation plan Step 1 — single-document config check.

Run against one known digital-native PDF with a table to confirm the
converter config (table structure, cell matching, format whitelist) is
wired correctly before touching harder documents.

Usage: python 01_single_doc_config_check.py <path-to-pdf>
"""

import sys
from pathlib import Path

from common import build_converter, report_writer, save_document_content


def main():
    if len(sys.argv) != 2:
        print("Usage: python 01_single_doc_config_check.py <path-to-pdf>")
        sys.exit(1)

    doc_path = Path(sys.argv[1])
    if not doc_path.exists():
        print(f"File not found: {doc_path}")
        sys.exit(1)

    converter = build_converter()
    result = converter.convert(doc_path)
    doc = result.document
    content_paths = save_document_content(doc, doc_path.stem)

    with report_writer("01_single_doc_config_check") as (emit, report_path):
        emit(f"Document: {doc_path.name}")
        emit(f"Status: {result.status}")
        emit(f"Pages: {len(doc.pages)}")
        emit(f"Tables detected: {len(doc.tables)}")
        emit(f"Text/other elements: {len(doc.texts)}")
        emit(f"Content saved to: {content_paths['markdown']}")
        emit(f"Full structured export: {content_paths['json']}")

        for i, table in enumerate(doc.tables):
            df = table.export_to_dataframe(doc=doc)
            emit(f"\n--- Table {i} ({df.shape[0]} rows x {df.shape[1]} cols) ---")
            emit(df.to_markdown())

    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    main()
