"""Stage 0 — scaffolding + basic converter smoke test.

Builds the DocumentConverter per Documents/EXTRACTION_APPROACH.md Sections 2-3
(Docling + RapidOCR, TableFormer ACCURATE, cell matching, full-page OCR) and
converts a single document end-to-end: text + table structure only, no
picture/Gemini pipeline (Section 9 is a later stage).

Usage:
    python -m extraction_pipeline.stage0_setup.run_stage0 <path-to-document>
"""

import sys
from pathlib import Path

from extraction_pipeline.utils.config import ExtractionConfig
from extraction_pipeline.utils.converter import build_converter
from extraction_pipeline.utils.io import report_writer, save_document_content


def run(source_path: Path) -> None:
    with report_writer("stage0") as (emit, report_path):
        emit(f"Stage 0 — converting: {source_path}")

        config = ExtractionConfig()
        converter = build_converter(config)

        result = converter.convert(str(source_path))
        doc = result.document

        emit(f"Status: {result.status}")
        emit(f"Pages: {len(doc.pages)}")
        emit(f"Tables detected: {len(doc.tables)}")
        emit(f"Pictures detected: {len(doc.pictures)}")

        paths = save_document_content(doc, source_path.stem)
        emit(f"Markdown written to: {paths['markdown']}")
        emit(f"JSON written to: {paths['json']}")
        emit(f"Report written to: {report_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m extraction_pipeline.stage0_setup.run_stage0 <path-to-document>")
        sys.exit(1)

    run(Path(sys.argv[1]))
