# Extraction v1 — test harness

Implements the validation plan from `Documents/EXTRACTION_APPROACH.md` Section 5.

## Setup

```
pip install -r requirements.txt
```

Drop test documents into `samples/` (PDFs, DOCX, PPTX, HTML, images, CSV, MD).

## OCR engine (Section 4 open question — resolved)

This Docling version has no native PaddleOCR options class (only `EasyOcrOptions`,
`TesseractOcrOptions`, `RapidOcrOptions`, `OcrMacOptions`, and two hosted options
exist in `docling.datamodel.pipeline_options`). `common.py` uses **RapidOCR**
instead — it runs PaddleOCR's own detection/recognition models via ONNX runtime,
making it the closest first-class equivalent without writing a custom OCR
backend wrapper.

## Output

Every script writes its run output to a timestamped file under
`output/reports/<script_name>_<timestamp>.txt` by default (in addition to
printing to console), via the shared `report_writer()` helper in `common.py`.

Scripts that convert documents (`01`, `02`, `04`) also save the **actual
extracted content** for every converted file via `save_document_content()`:
- `output/content/<stem>.md` — readable Markdown export
- `output/content/<stem>.json` — full structured `DoclingDocument` export (the Section 6 output contract)

Table exports (`03`) and per-format contract exports (`05`) go to their own
subfolders under `output/` as before.

## Scripts (run in this order)

| Script | Validation plan step | What it checks |
|---|---|---|
| `01_single_doc_config_check.py <pdf>` | Step 1 | Config (table structure, cell matching) wired correctly on one known-good PDF |
| `02_multi_format_smoke_test.py` | Step 2 | Every file in `samples/` converts without error, across formats |
| `03_table_extraction.py [files...]` | Step 3 | Exports every detected table to HTML + CSV in `output/tables/` |
| `04_batch_convert.py` | Step 5 | Full `samples/` set through `convert_all(raises_on_error=False)`, pass/fail summary |
| `05_output_contract_check.py <file1> <file2>` | Section 6 (output contract) | Diffs element-type structure across two different input formats to confirm schema uniformity |

Step 4 (structural correctness check) is manual: open each `output/tables/*.html`
next to the source document page and check cell merges, header association,
and row/column order, per the checklist in `EXTRACTION_APPROACH.md` Section 5.

## Not yet in v1

- The coordinate-based reconstruction fallback (`EXTRACTION_APPROACH.md` Section 8) — only build if Step 4 shows TableFormer failing on scanned dense-form pages
