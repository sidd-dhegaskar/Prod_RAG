"""Shared converter config for the extraction v1 test scripts.

Config decisions here mirror Documents/EXTRACTION_APPROACH.md Section 3.
"""

import json
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    RapidOcrOptions,
    TableFormerMode,
    TableStructureOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption

REPORTS_DIR = Path(__file__).parent / "output" / "reports"
CONTENT_DIR = Path(__file__).parent / "output" / "content"


@contextmanager
def report_writer(script_name: str):
    """Writes every emit(...) call to both stdout and a timestamped report
    file under output/reports/, so run output is saved by default."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = REPORTS_DIR / f"{script_name}_{timestamp}.txt"

    with report_path.open("w", encoding="utf-8") as f:
        def emit(*args, sep=" ", end="\n"):
            text = sep.join(str(a) for a in args) + end
            sys.stdout.write(text)
            f.write(text)

        yield emit, report_path


def save_document_content(doc, stem: str) -> dict:
    """Saves the actual extracted content (not just summary stats) for one
    converted document: Markdown for readability, full DoclingDocument JSON
    for the complete structured output (per EXTRACTION_APPROACH.md Section 6
    output contract). Returns the paths written."""
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)

    md_path = CONTENT_DIR / f"{stem}.md"
    json_path = CONTENT_DIR / f"{stem}.json"

    md_path.write_text(doc.export_to_markdown(traverse_pictures=True), encoding="utf-8")
    json_path.write_text(json.dumps(doc.export_to_dict(), indent=2), encoding="utf-8")

    return {"markdown": md_path, "json": json_path}

ALLOWED_FORMATS = [
    InputFormat.PDF,
    InputFormat.IMAGE,
    InputFormat.DOCX,
    InputFormat.HTML,
    InputFormat.PPTX,
    InputFormat.CSV,
    InputFormat.MD,
]

# Resolved Section 4 open question: this Docling version has no native
# PaddleOCR options class (confirmed by inspecting docling.datamodel.
# pipeline_options — only EasyOcrOptions, TesseractOcrOptions,
# RapidOcrOptions, OcrMacOptions, KserveV2OcrOptions, NemotronOcrOptions
# exist). RapidOCR runs PaddleOCR's own detection/recognition models via
# ONNX runtime, so it's used here as the closest first-class equivalent
# instead of writing a custom OCR backend wrapper.


def build_converter(force_full_page_ocr: bool = True) -> DocumentConverter:
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options = TableStructureOptions(
        mode=TableFormerMode.ACCURATE,
        do_cell_matching=True,
    )
    # Default True: Docling's page-level OCR skip (only OCR pages with no
    # digital text layer) starves text baked into pictures/graphics on
    # otherwise digital-native pages — confirmed via 06_compare_full_page_ocr.py
    # to drop category labels a shallow pass misses (low-contrast/reverse
    # text). force_full_page_ocr=True re-OCRs every page as a full image,
    # trading some redundant work on already-correct native text for
    # completeness on picture-embedded text.
    pipeline_options.ocr_options = RapidOcrOptions(force_full_page_ocr=force_full_page_ocr)

    return DocumentConverter(
        allowed_formats=ALLOWED_FORMATS,
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        },
    )
