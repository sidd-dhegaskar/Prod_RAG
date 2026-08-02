# Extraction — Approach Document

Scope: the parsing/extraction piece of Layer 1 (Ingestion & preprocessing) only. Chunking, ACL tagging, embedding, and everything downstream are out of scope for this document.

## 1. Goal

Extract content from all supported source document types with **table structure preserved** — merged cells, spanned headers, and row/column relationships intact — not flattened into plain text. Beyond tables, extraction must also preserve content and context from **pictures** (charts, diagrams, scanned figures) — including content that plain OCR cannot read at all (icons/symbols used in place of text) — without regressing the table-fidelity goal above or introducing unbounded cost/latency. Section 9 covers the picture-specific approach; Sections 2–8 cover text/table extraction.

## 2. Tool choice

| Component | Choice | Why |
|---|---|---|
| Parser | **Docling** | Best-in-class structural table recognition (TableFormer), which is the priority requirement here. Narrower format coverage than Unstructured.io, but table fidelity outweighs breadth for this use case. Evaluated against Unstructured.io again during the picture-extraction investigation (Section 9) and reconfirmed: swapping parsers would cost the `DoclingDocument` output contract (Section 6) and format breadth for no gain on the actual open problems (OCR latency, symbolic content) — those are properties of OCR as a technique, not of which library wraps it. |
| OCR backend | **RapidOCR** | Plugs into Docling as the OCR engine for scanned/image-based pages and picture-embedded text. This Docling version has no native PaddleOCR options class (only `EasyOcrOptions`, `TesseractOcrOptions`, `RapidOcrOptions`, `OcrMacOptions`, `KserveV2OcrOptions`, `NemotronOcrOptions` exist — confirmed by inspecting `docling.datamodel.pipeline_options`). RapidOCR runs PaddleOCR's own detection/recognition models via ONNX runtime, so it's used as the closest first-class equivalent instead of writing a custom OCR backend wrapper. (Superseded the original PaddleOCR choice below this table — see Section 9.2 for the later, separate evaluation of PaddleOCR's full `PP-StructureV3` pipeline as a candidate for a different job, reading-order reconstruction, not as the OCR backend.) |

Docling and RapidOCR are not alternatives — RapidOCR is a component *inside* the Docling pipeline, used only for OCR on non-digital-native pages and pictures.

## 3. Configuration decisions

| Setting | Value | Reason |
|---|---|---|
| `do_table_structure` | `True` | Activates TableFormer; not always on by default. |
| `TableFormerMode` | `ACCURATE` | Slower than `FAST`, but materially better on merged cells and multi-row headers — required given the table-fidelity goal. |
| `TableStructureOptions(do_cell_matching=True)` | `True` | Ties recognized table cells back to actual OCR/text content — a separate setting from table-structure mode, confirmed via the `custom_convert` example. Without it, structure can be detected but not correctly populated with content. |
| OCR engine | `RapidOcrOptions` | Set via `pipeline_options.ocr_options`. See Section 2 — resolved from the originally planned PaddleOCR options class, which doesn't exist in this Docling version. |
| `force_full_page_ocr` | `True` | Docling's default only OCRs pages with no digital text layer, which starves text baked into pictures/graphics on otherwise digital-native pages. Confirmed via `06_compare_full_page_ocr.py`: default config missed low-contrast/reverse-text labels; full-page OCR recovered them. **Cost:** this is the dominant driver of the ~300s per-document OCR latency observed in testing, since it re-OCRs every page as a full image rather than only pages lacking a text layer — an accepted, deliberate completeness-over-speed tradeoff, not an oversight. |
| `export_to_markdown(traverse_pictures=True)` | `True` | The markdown export was silently dropping all picture-nested text regardless of OCR quality. Confirmed to be the larger of the two extraction-completeness fixes (0/8 → 7/8 test fragments recovered from this alone, before the `force_full_page_ocr` fix above added the last one). |
| Allowed formats | Explicit `allowed_formats` whitelist (PDF, IMAGE, DOCX, HTML, PPTX, CSV, MD) | Confirmed via the `run_with_formats` example — this is the actual mechanism for "support all kinds of data types." Each format can carry its own backend/pipeline (e.g. PDF → `StandardPdfPipeline` + `PyPdfiumDocumentBackend`; DOCX → `SimplePipeline`). |
| Output format | **HTML** (`table.export_to_html(doc=...)`) *and* **DataFrame** (`table.export_to_dataframe(doc=...)`) for any document containing tables | HTML preserves merged/spanned cells for human review; DataFrame gives a structured, diffable form for automated validation (row/column comparison against expected values) rather than eyeballing markup. Markdown is acceptable only for table-free content — it can't represent spans. |

All of the above is implemented in `Tests/extraction_v1/common.py`'s `build_converter()`.

## 4. Open questions

- What fraction of the source corpus is scanned/image-based vs. digital-native? Determines how much OCR tuning effort is worth investing now vs. later, and how much the `force_full_page_ocr` latency cost actually matters at corpus scale.
- Do we have representative "hard" documents (merged headers, nested tables, scanned tables) to validate against before this is trusted in the pipeline?
- What fraction of the corpus contains multi-panel pictures (charts/figures grouped in a grid) or symbolic/iconographic content (Section 9)? Determines how much the picture-triage work in Section 9 actually matters vs. how much of the corpus never hits it.

## 5. Validation plan

Reference examples (Docling docs): [`batch_convert`](https://docling-project.github.io/docling/_generated/examples/batch_convert/), [`custom_convert`](https://docling-project.github.io/docling/_generated/examples/custom_convert/), [`run_with_formats`](https://docling-project.github.io/docling/_generated/examples/run_with_formats/), [`export_tables`](https://docling-project.github.io/docling/_generated/examples/export_tables/).

Before this extraction step is considered ready to feed downstream work:

1. **Single-document config check** — using the `custom_convert` pattern, build a `DocumentConverter` with `do_table_structure=True`, `TableFormerMode.ACCURATE`, `do_cell_matching=True`, and RapidOCR as the OCR engine. Run against one known digital-native PDF with a table to confirm the config is wired correctly before touching harder documents.
2. **Multi-format smoke test** — using the `run_with_formats` pattern, set an explicit `allowed_formats` whitelist and confirm one sample file per format (PDF, DOCX, PPTX, HTML, image, CSV, MD) converts without error. This validates format coverage, not table fidelity.
3. **Table extraction on hard documents** — collect 3–5 representative documents with the gnarliest real tables in the corpus (merged headers, nested tables, and — if available — scanned tables requiring OCR). Using the `export_tables` pattern, export each detected table to both HTML and DataFrame/CSV.
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
| Extraction method / provenance (picture elements only) | Carried natively by Docling's own schema — `created_by` and `confidence` on `BasePrediction` (the base class of `PictureMeta`'s sub-fields). No custom field needed; see Section 9.3. |

**Format-uniformity check:** `run_with_formats` uses a different backend per input type (PDF → `StandardPdfPipeline`, DOCX → `SimplePipeline`, etc.), but all should converge on the same `DoclingDocument` schema. Verify this directly during testing — convert one sample PDF and one sample DOCX and diff their element structure (types, metadata fields present) rather than assuming uniformity holds across backends.

**Explicitly not covered by this contract:** ACL/permission metadata (attached in the next Layer 1 step, not by extraction) and chunk boundaries (decided by the chunker, not by extraction) — extraction's job ends at producing a well-typed, well-tagged `DoclingDocument`, not at deciding how it gets split or access-controlled.

## 7. Explicitly out of scope here

- Chunking strategy for tables (keeping header+rows atomic through the splitter) — deferred to the chunking phase.
- ACL/metadata tagging.
- Non-document sources (audio/video transcription, structured data/API connectors).
- Embedding, indexing, retrieval.

## 8. Fallback path for scanned/OCR'd tables: coordinate-based reconstruction

For scanned pages (the RapidOCR path), TableFormer is a trained structure-detection model working off the page image — it can underperform on dense forms with no drawn table lines (e.g. ACORD/insurance-style forms), which is a known hard case for structure models in general.

An alternative, evaluated but not yet adopted: reconstruct table structure directly from OCR's raw `(text, bounding_box)` output via coordinate clustering (column-alignment detection across lines) instead of a second structure model. Cheap (pure CPU post-processing on boxes RapidOCR already produces, no extra GPU pass) and specifically validated against dense forms without ruled lines — the exact case where image-based structure models struggle.

**Status:** not implemented. Treat as the fallback to reach for if Step 4 (structural correctness check) shows TableFormer failing specifically on scanned dense-form pages. Do not implement pre-emptively — validate TableFormer's actual failure rate on real scanned samples first (Section 4's open question on scanned-vs-digital split needs an answer before this is worth building).

## 9. Picture pipeline: classifier-gated triage + Gemini extraction

### 9.1 The problem this addresses

Two distinct failure classes were found via manual inspection (`08_visualize_extraction.py`) on pictures Docling/RapidOCR extract text from:

- **Reading order on multi-panel pictures** — OCR reads glyphs correctly but in the wrong sequence when a picture contains multiple independent panels (e.g. a 2×2 grid of charts). A hand-rolled nearest-anchor heuristic (`panel_reconstruction.py`) fixed the simple 2-panel case but broke on a genuine 2×2 grid. **Explicitly out of scope for this pipeline** — see 9.7.
- **Symbolic/iconographic content** — icons (e.g. up-arrow/dash/"n.a." used in place of numeric values) are not in any OCR engine's character set. This is data loss, not misordering. Confirmed on two separate OCR-family engines (RapidOCR, and PaddleOCR's PP-StructureV3 pipeline — see 9.2): both extract 0 of ~42 icon-coded data cells on the same sample table. **This is the problem this pipeline solves.**

### 9.2 Prior evaluation (context, not part of the build)

PaddleOCR/PP-StructureV3 was evaluated as a stronger reading-order engine and confirmed to fix the multi-panel case but have zero effect on the icon case — different failure class, no amount of better OCR/layout modeling closes it. **Decision: not adopted.** Docling remains the extraction framework (format breadth, TableFormer, the `DoclingDocument` schema in Section 6 all depend on it). Reference only: `Tests/extraction_v1/09_visualize_ppstructure.py` and `output/visualizations/*-ppstructure-compare.png`.

Unstructured.io was also considered as a full parser swap and rejected on the same grounds: it is the same category of tool (OCR-backed parser), so it does not solve the icon-recognition gap either, and swapping would cost the `DoclingDocument` schema and format breadth for no gain.

### 9.3 Architecture

```
DocumentConverter.convert()                         [Docling + RapidOCR, existing config — Sections 2-3]
        │
        ├─ text, headings, lists, native tables ──────────────────────────► unchanged, already working
        │
        └─ doc.pictures: list[PictureItem]
                │  each has .meta.classification (Docling's own classifier, in-process, already run)
                ▼
        route_picture(picture) -> bool                [pure Python, no new dependency]
                │
        ┌───────┴────────┐
        │                │
    not flagged      flagged
        │                │
        │           picture.get_image(doc) -> PIL.Image
        │                │
        │           call_gemini(image) -> structured JSON result
        │                │
        │           write result onto picture.meta (.description or .tabular_chart)
        │                │
        └───────┬────────┘
                ▼
        doc.export_to_dict()                          [Section 6 output contract — unchanged shape]
```

One Docling conversion pass produces the whole document, including picture crops and classification — no second parsing pass. Only flagged pictures make an external call. Everything else in the document is untouched by this pipeline.

### 9.4 Stage 1 — Triage (in-process, no new dependency)

Docling's built-in picture classifier does this for free as part of the existing `convert()` call:

```python
pipeline_options.do_picture_classification = True
pipeline_options.generate_picture_images = True   # required for picture.get_image(doc) later
pipeline_options.do_picture_description = False    # bypassed — Section 9.6 explains why
pipeline_options.do_chart_extraction = False        # bypassed — same reason
```

Each `PictureItem` then carries `picture.meta.classification: PictureClassificationMetaField`, with `predictions: list[PictureClassificationPrediction(class_name, confidence, created_by)]`. The label set is Docling's own taxonomy (`docling_core.types.doc.labels.PictureClassificationLabel`) — confirmed to include, among others: `bar_chart`, `line_chart`, `pie_chart`, `scatter_plot`, `box_plot`, `heatmap`, `flow_chart`, `table`, `icon`, `logo`, `photograph`, `qr_code`, `bar_code`, `signature`, `stamp`, `screenshot`, `other`.

Routing is a plain function over that prediction list:

```python
def needs_gemini_extraction(picture: PictureItem, flag_labels: set[str], min_confidence: float) -> bool:
    classification = picture.meta.classification if picture.meta else None
    if not classification or not classification.predictions:
        return True  # no classifier signal — fail open, don't silently skip a picture
    top = max(classification.predictions, key=lambda p: p.confidence)
    return top.class_name in flag_labels and top.confidence >= min_confidence
```

**To decide before/while building** (see 9.7): which labels go in `flag_labels` (charts/tables/icons clearly yes; photograph/logo/signature/qr_code clearly no — a handful of labels are genuinely ambiguous and need a real sample to judge), and where `min_confidence` sits. Start with a permissive threshold (fail toward escalating, not toward silent OCR-only fallback) and tighten using real corpus data once available — do not hand-tune against the two known sample PDFs alone, per Section 4's open question on corpus composition.

### 9.5 Stage 2 — Extraction call (Gemini, external)

For each flagged `PictureItem`:

```python
image: PIL.Image.Image = picture.get_image(doc)   # already-cropped picture, confirmed working in 08_/09_ scripts
```

Send `image` to the Gemini API with **structured output** (`response_schema`), not a free-text captioning prompt — this is the concrete resolution of the hallucination-risk concern raised earlier: constrain the model to a closed shape instead of letting it narrate. Draft schema (to be refined against real samples, not finalized here):

```python
{
  "type": "object",
  "properties": {
    "content_type": {"type": "string", "enum": ["table", "chart", "icon_legend_table", "other"]},
    "title": {"type": "string"},
    "extracted_text": {"type": "string"},        # used when content_type == "other"
    "table_rows": {                                # used when content_type in {"table", "icon_legend_table"}
      "type": "array",
      "items": {"type": "array", "items": {"type": "string"}}
    },
    "notes": {"type": "string"}                    # model's own caveats — informational only, not a trust signal
  },
  "required": ["content_type"]
}
```

**To decide before building:** exact schema shape (the draft above is a starting point, not final — needs testing against the page-3 chart panels and page-4 icon table specifically), the prompt text, which Gemini model/API version, and how the SDK call itself is structured (`google-genai` package — not yet installed or tested in this repo; confirm the current SDK name/import path when building, since Google's Python SDK naming has changed across versions).

### 9.6 Stage 3 — Writing the result back (Docling's native schema, no custom types)

`PictureItem.meta` (`PictureMeta`) already has the exact fields needed — confirmed by inspecting `docling_core.types.doc.document` directly, no custom annotation class required (the older `PictureItem.annotations` list is deprecated in this Docling version; use `meta`):

```python
from docling_core.types.doc.document import DescriptionMetaField, TabularChartMetaField
from docling_core.types.doc.table_data import TableData  # exact import path to confirm when building

if result.content_type in ("table", "icon_legend_table"):
    picture.meta.tabular_chart = TabularChartMetaField(
        title=result.title,
        chart_data=rows_to_table_data(result.table_rows),  # maps into Docling's own TableData —
                                                              # the SAME type TableFormer populates for
                                                              # real tables, so downstream (chunking,
                                                              # embedding) sees one table shape, not two
        created_by="gemini-<model-version>",
        confidence=result.confidence if available,
    )
else:
    picture.meta.description = DescriptionMetaField(
        text=result.extracted_text,
        created_by="gemini-<model-version>",
    )
```

This is what makes the extraction method/provenance row in Section 6's table true without any schema extension: `created_by` distinguishes Gemini-derived content from Docling/TableFormer-derived content (which carries Docling's own model names) by value convention alone. `picture`'s own `prov` (page number, bbox) already gives the citation link back to the source location — no new linkage mechanism needed.

`doc.export_to_dict()` picks this up automatically since it's a native field, not a bolt-on — the Section 6 output contract's shape is unchanged.

### 9.7 Explicitly out of scope for this pipeline

- **Multi-panel reading order** (9.1's first failure class) — this pipeline does not attempt to fix it. A capable VLM reading a picture as a whole image plausibly sidesteps the problem as a side effect (it never had Docling's line-by-line OCR ordering step to begin with), but this is an unconfirmed possible bonus, not a design goal — do not build around the assumption it's fixed until observed directly on a flagged multi-panel picture.
- **Embedding/vectorization effects of `tabular_chart` vs. `description` content** — a real open question (a table-shaped payload and a prose payload will embed differently) but belongs to the chunking/embedding design (Layer 1's next step / Layer 2), not this document. Deferred.
- **Classification threshold tuning and Gemini schema finalization against a real corpus** — both are called out above as pre-build decisions but are inherently iterative; treat the first cut of both as a hypothesis to test against samples, not a final answer.

### 9.8 Build checklist (for picking this up in a fresh session)

1. Set `do_picture_classification=True`, `generate_picture_images=True` in `common.py`'s `build_converter()` (or a variant of it) and confirm `picture.meta.classification.predictions` is populated on a real sample (start with `samples/022-article-A002-en.pdf`, pictures 2 and 3 — the known 2×2 grid and icon table).
2. Decide and hard-code an initial `flag_labels` set and `min_confidence` (9.4) — a starting guess is fine, it's meant to be revisited.
3. Install and confirm the current Google Gemini Python SDK package name/import path; write a minimal script that sends one flagged picture crop (e.g. the page-4 icon table) and gets back structured JSON matching a first-draft schema (9.5).
4. Write the result onto `picture.meta` per 9.6; confirm via `doc.export_to_dict()` that `created_by` and the extracted content round-trip correctly.
5. Visual/manual check against the source image (reuse the `08_/09_` visualization pattern) before trusting this on more documents.
