"""Sanity check for the picture-embedded-text gap (see conversation /
EXTRACTION_APPROACH.md): does force_full_page_ocr=True recover text that's
baked into a picture/graphic on an otherwise digital-native page?

Converts the same document twice — default config vs. force_full_page_ocr
— and compares markdown length, picture charspans, and whether known
chart-text fragments show up. This is a cheap recoverability test, not a
correctness/layout test: even if the text comes back, it may be in the
wrong reading order (see EXTRACTION_APPROACH.md Section 8 on why a 2x2
multi-panel chart needs coordinate-based reconstruction, not just OCR).

Usage: python 06_compare_full_page_ocr.py <path-to-pdf> [expected-fragment ...]
If no fragments given, defaults to fragments from the stock-market chart
page used during testing.
"""

import sys
from pathlib import Path

from common import build_converter, report_writer, save_document_content

DEFAULT_FRAGMENTS = [
    "Very large", "Very small", "Very volatile", "Very stable",
    "Very developed", "Very liquid", "Zimbabwe", "Argentina",
]


def picture_charspans(doc):
    return [p.prov[0].charspan if p.prov else None for p in doc.pictures]


def main():
    if len(sys.argv) < 2:
        print("Usage: python 06_compare_full_page_ocr.py <path-to-pdf> [expected-fragment ...]")
        sys.exit(1)

    doc_path = Path(sys.argv[1])
    fragments = sys.argv[2:] or DEFAULT_FRAGMENTS

    with report_writer("06_compare_full_page_ocr") as (emit, report_path):
        emit(f"Document: {doc_path.name}")
        emit(f"Checking for fragments: {fragments}\n")

        for label, force in [("default (page-level OCR skip)", False), ("force_full_page_ocr=True", True)]:
            emit(f"=== {label} ===")
            converter = build_converter(force_full_page_ocr=force)
            result = converter.convert(doc_path)
            doc = result.document

            stem = f"{doc_path.stem}__force_full_page_ocr={force}"
            content_paths = save_document_content(doc, stem)
            md_text = content_paths["markdown"].read_text(encoding="utf-8")

            emit(f"Status: {result.status}")
            emit(f"Markdown length: {len(md_text)} chars")
            emit(f"Picture charspans: {picture_charspans(doc)}")

            found = [f for f in fragments if f in md_text]
            missing = [f for f in fragments if f not in md_text]
            emit(f"Fragments FOUND ({len(found)}/{len(fragments)}): {found}")
            emit(f"Fragments MISSING: {missing}")
            emit(f"Saved to: {content_paths['markdown']}\n")

        emit("Interpretation: if force_full_page_ocr recovers the fragments, the text is")
        emit("recoverable but reading order is not yet validated — check the saved .md")
        emit("manually to see whether the 4 chart panels' text is interleaved/scrambled")
        emit("(expected, per EXTRACTION_APPROACH.md Section 8) before deciding whether")
        emit("full-page OCR alone is sufficient or the coordinate-reconstruction step is")
        emit("still needed.")

    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    main()
