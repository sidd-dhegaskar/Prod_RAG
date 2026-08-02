# Extraction — Approach Document

Scope: the parsing/extraction piece of Layer 1 (Ingestion & preprocessing) only. Chunking, ACL tagging, embedding, and everything downstream are out of scope for this document.

## 1. Goal

Extract content from all supported source document types with **table structure preserved** — merged cells, spanned headers, and row/column relationships intact — not flattened into plain text.

## 2. Tool choice

| Component | Choice | Why |
|---|---|---|
| Parser | **Docling** | Best-in-class structural table recognition (TableFormer), which is the priority requirement here. Narrower format coverage than Unstructured.io, but table fidelity outweighs breadth for this use case. |
| OCR backend | **PaddleOCR** | Plugs into Docling as the OCR engine for scanned/image-based pages. Only invoked when a page has no embedded text layer. Stronger than Docling's default (EasyOCR) on dense tables and non-Latin scripts. |

Docling and PaddleOCR are not alternatives — PaddleOCR is a component *inside* the Docling pipeline, used only for OCR on non-digital-native pages.

## 3. Configuration decisions

| Setting | Value | Reason |
|---|---|---|
| `do_table_structure` | `True` | Activates TableFormer; not always on by default. |
| `TableFormerMode` | `ACCURATE` | Slower than `FAST`, but materially better on merged cells and multi-row headers — required given the table-fidelity goal. |
| `TableStructureOptions(do_cell_matching=True)` | `True` | Ties recognized table cells back to actual OCR/text content — a separate setting from table-structure mode, confirmed via the `custom_convert` example. Without it, structure can be detected but not correctly populated with content. |
| OCR engine | PaddleOCR | Set via `pipeline_options.ocr_options`. Confirm the PaddleOCR options class name exists in our pinned Docling version — the documented `custom_convert` example shows EasyOCR/Tesseract options classes directly; PaddleOCR support needs to be checked against that module before relying on it. |
| OCR scope | On-demand (default) | Runs PaddleOCR only on pages without a text layer, not full-page OCR on every page. Cheaper and correct for a mixed digital/scanned corpus. |
| Allowed formats | Explicit `allowed_formats` whitelist (PDF, IMAGE, DOCX, HTML, PPTX, ASCIIDOC, CSV, MD) | Confirmed via the `run_with_formats` example — this is the actual mechanism for "support all kinds of data types." Each format can carry its own backend/pipeline (e.g. PDF → `StandardPdfPipeline` + `PyPdfiumDocumentBackend`; DOCX → `SimplePipeline`). |
| Output format | **HTML** (`table.export_to_html(doc=...)`) *and* **DataFrame** (`table.export_to_dataframe(doc=...)`) for any document containing tables | HTML preserves merged/spanned cells for human review; DataFrame gives a structured, diffable form for automated validation (row/column comparison against expected values) rather than eyeballing markup. Markdown is acceptable only for table-free content — it can't represent spans. |

## 4. Open questions

- What fraction of the source corpus is scanned/image-based vs. digital-native? Determines how much PaddleOCR tuning effort is worth investing now vs. later.
- Which Docling version are we pinning to, and does its `ocr_options` module expose a PaddleOCR options class directly, or does it require a custom OCR backend wrapper?
- Do we have representative "hard" documents (merged headers, nested tables, scanned tables) to validate against before this is trusted in the pipeline?

## 5. Validation plan

Reference examples (Docling docs): [`batch_convert`](https://docling-project.github.io/docling/_generated/examples/batch_convert/), [`custom_convert`](https://docling-project.github.io/docling/_generated/examples/custom_convert/), [`run_with_formats`](https://docling-project.github.io/docling/_generated/examples/run_with_formats/), [`export_tables`](https://docling-project.github.io/docling/_generated/examples/export_tables/).

Before this extraction step is considered ready to feed downstream work:

1. **Single-document config check** — using the `custom_convert` pattern, build a `DocumentConverter` with `do_table_structure=True`, `TableFormerMode.ACCURATE`, `do_cell_matching=True`, and PaddleOCR as the OCR engine. Run against one known digital-native PDF with a table to confirm the config is wired correctly before touching harder documents.
2. **Multi-format smoke test** — using the `run_with_formats` pattern, set an explicit `allowed_formats` whitelist and confirm one sample file per format (PDF, DOCX, PPTX, HTML, image, CSV, MD) converts without error. This validates format coverage, not table fidelity.
3. **Table extraction on hard documents** — collect 3–5 representative documents with the gnarliest real tables in the corpus (merged headers, nested tables, and — if available — scanned tables requiring PaddleOCR). Using the `export_tables` pattern, export each detected table to both HTML and DataFrame/CSV.
4. **Structural correctness check** — manually inspect each table's HTML output against the source document (cell merges, header association, row/column order). Use the DataFrame/CSV export to spot-check cell values programmatically where a known-correct reference exists.
5. **Batch run** — once single-document config is validated, run the full test set through `convert_all(..., raises_on_error=False)` (the `batch_convert` pattern) so failures on individual documents don't block seeing results for the rest; review the summarized errors afterward.
6. Note failure patterns (if any) and decide whether they need further `ACCURATE`-mode tuning, a different OCR engine, or the coordinate-based column-alignment fallback (see Section 8) for scanned pages specifically.

## 6. Output contract for downstream stages

This section defines what extraction hands off to the next steps in Layer 1 (ACL/metadata tagging, structure-aware chunking) — not new processing, just the shape of the handoff.

**Serialization format:** `DoclingDocument`'s native structured export (`export_to_dict()` → JSON), not a flattened HTML or Markdown string. JSON preserves each element (paragraph, table, heading, list item, figure) as a separate typed object, so downstream stages can make per-element decisions instead of re-parsing a flattened document to rediscover structure extraction already knew.

**Per-element metadata to carry forward:**

| Field | Purpose |
|---|---|
| Source document ID / filename | Provenance; required for citations (Layer 4) and Langfuse traces (Layer 6 of the main design doc) |
| Page number(s) | Same — citation and trace granularity |
| Element type (table / paragraph / heading / list / figure) | Lets the chunker treat tables as atomic instead of splitting mid-row — depends on extraction preserving this tag now, since it can't be recovered later from flattened text |
| Reading order / sequence index | Keeps reassembly and citation-to-location correct |
| Heading hierarchy / section path | Required input for the structure-aware chunking already committed to in the main design doc's Layer 1 — the chunker needs sections to chunk *by* |
| Table payload | Both `export_to_html()` and `export_to_dataframe()` attached to the table element itself, not merged into surrounding prose text |

**Format-uniformity check:** `run_with_formats` uses a different backend per input type (PDF → `StandardPdfPipeline`, DOCX → `SimplePipeline`, etc.), but all should converge on the same `DoclingDocument` schema. Verify this directly during testing — convert one sample PDF and one sample DOCX and diff their element structure (types, metadata fields present) rather than assuming uniformity holds across backends.

**Explicitly not covered by this contract:** ACL/permission metadata (attached in the next Layer 1 step, not by extraction) and chunk boundaries (decided by the chunker, not by extraction) — extraction's job ends at producing a well-typed, well-tagged `DoclingDocument`, not at deciding how it gets split or access-controlled.

## 7. Explicitly out of scope here

- Chunking strategy for tables (keeping header+rows atomic through the splitter) — deferred to the chunking phase.
- ACL/metadata tagging.
- Non-document sources (audio/video transcription, structured data/API connectors).
- Embedding, indexing, retrieval.

## 8. Fallback path for scanned/OCR'd tables: coordinate-based reconstruction

For scanned pages (PaddleOCR path), TableFormer is a trained structure-detection model working off the page image — it can underperform on dense forms with no drawn table lines (e.g. ACORD/insurance-style forms), which is a known hard case for structure models in general.

An alternative, evaluated but not yet adopted: reconstruct table structure directly from OCR's raw `(text, bounding_box)` output via coordinate clustering (column-alignment detection across lines) instead of a second structure model. Cheap (pure CPU post-processing on boxes PaddleOCR already produces, no extra GPU pass) and specifically validated against dense forms without ruled lines — the exact case where image-based structure models struggle.

**Status:** not implemented. Treat as the fallback to reach for if Step 4 (structural correctness check) shows TableFormer failing specifically on scanned dense-form pages. Do not implement pre-emptively — validate TableFormer's actual failure rate on real scanned samples first (Section 4's open question on scanned-vs-digital split needs an answer before this is worth building).
