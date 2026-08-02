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
| Extraction method / provenance (picture elements only) | **Not yet implemented** — planned per Section 9: tags picture-derived content as `ocr` vs. `gemini`-extracted, plus a link back to the stored picture crop. Required before Section 9's Gemini path can hand off usable, auditable results downstream; not required for text/table elements, which are OCR/TableFormer-derived by construction. |

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

## 9. Picture triage + Gemini extraction (decided direction, not yet built)

### 9.1 The problem this addresses

Two distinct failure classes were found via manual inspection (`08_visualize_extraction.py`) on pictures Docling/RapidOCR extract text from:

- **Reading order on multi-panel pictures** — OCR reads glyphs correctly but in the wrong sequence when a picture contains multiple independent panels (e.g. a 2×2 grid of charts). A hand-rolled nearest-anchor heuristic (`panel_reconstruction.py`) fixed the simple 2-panel case but broke on a genuine 2×2 grid.
- **Symbolic/iconographic content** — icons (e.g. up-arrow/dash/"n.a." used in place of numeric values) are not in any OCR engine's character set. This is data loss, not misordering: PaddleOCR/PP-StructureV3 was evaluated specifically as a stronger reading-order engine (see below) and confirmed to *fix* the first problem but have *no effect* on the second — different failure class, no amount of better OCR/layout modeling closes it.

### 9.2 PaddleOCR / PP-StructureV3 evaluation — result

Tested head-to-head against `panel_reconstruction.py` on the two hardest pictures in `samples/022-article-A002-en.pdf`:

- **2×2 chart grid (page 3):** PP-StructureV3 correctly separated all 4 panels with no cross-panel bleed, and correctly typed two panels as `table` (with rowspan/colspan HTML) and two as `chart`/`image`. Confirmed a real win over the heuristic.
- **Icon table (page 4):** PP-StructureV3 recovered table structure (headers, most country names) but **every icon/symbol data cell came back empty** — same outcome as RapidOCR. Confirms the icon-recognition gap is orthogonal to which OCR/layout engine is used.
- **Table-structure quality caveat:** on the same samples, PP-StructureV3's table output was not clearly better than Docling's TableFormer — one table lost a data row (Argentina) entirely, and another had a long tail of spurious empty rows. Not validated as a TableFormer replacement.

**Decision: not adopted as a pipeline swap.** Docling stays the extraction framework (format breadth, TableFormer, the `DoclingDocument` output contract in Section 6 all depend on it). See `Tests/extraction_v1/09_visualize_ppstructure.py` for the comparison script and `output/visualizations/*-ppstructure-compare.png` for the visual evidence, kept for reference if this is revisited.

### 9.3 Chosen direction: classifier-gated triage, Gemini for extraction

Rather than routing all pictures through a VLM (rejected earlier — cost/latency/hallucination risk at corpus scale for content OCR already handles correctly), or building a custom confidence-signal detector from scratch, the chosen approach reuses one piece of Docling's native picture-handling stack and pairs it with an external call for the actual extraction:

1. **Triage — Docling's built-in picture classifier** (`do_picture_classification=True`, `DocumentPictureClassifierOptions`). Small, in-process, HF-Transformers-based image classifier — not a VLM. Tags each picture by type (photo, diagram, chart, logo, etc.) with a confidence score, at negligible cost. This is the routing signal: pictures classified as chart/diagram/table-like (as opposed to e.g. decorative photos/logos) are candidates for escalation.
2. **Extraction — Gemini API**, called directly from custom orchestration code for flagged pictures only, **not** via Docling's own `do_picture_description`/`do_chart_extraction` stages. Bypassing Docling's built-in description stage avoids standing up a local OpenAI-compatible server just to make a call Docling would make anyway, and keeps the extraction call (prompt, output format, provenance tagging) fully under direct control.

**Deliberate architecture exception:** Gemini is a hosted API, not self-hosted — this is a conscious, scoped deviation from `RAG_SYSTEM_DESIGN.md`'s self-hosted-stack default, limited to this one sub-step (flagged pictures only, not the general LLM/embedding/reranking path). Recorded in `RAG_SYSTEM_DESIGN.md`'s consistency-choices section.

### 9.4 How this resolves 9.1

- **Symbolic/iconographic content** (the primary target): resolved by design, not yet by implementation. Every picture the classifier flags as chart/diagram/table-like gets routed to Gemini instead of relying on OCR, so icon-coded data (the page-4 case: 0/42 cells recovered by either RapidOCR or PP-StructureV3) is no longer dependent on a character-set match at all — Gemini reads the image directly. This closes the gap structurally: the previous approaches all failed for the same underlying reason (OCR-family engines, regardless of which one), and this direction is the first one that isn't OCR-family.
- **Reading order on multi-panel pictures**: explicitly **not** addressed by this direction — see 9.5. A capable VLM reading a picture as a whole image (rather than a sequence of OCR line-boxes) plausibly sidesteps the reading-order problem as a side effect, since it never had Docling's line-by-line ordering step to begin with — but this has not been tested and is not the reason this path was chosen, so treat it as an unconfirmed possible bonus, not a claimed fix.
- **Cost/latency, kept bounded:** because the classifier gates which pictures reach Gemini, the majority case (clean digital text and tables, already handled correctly by Docling/TableFormer/RapidOCR) never touches the hosted API — only the minority flagged as picture-like content does. This is what keeps the design consistent with the "simpler, not accounting for every scenario OCR struggles with" preference: the pipeline doesn't grow a special case for every failure found by inspection, it grows one routing decision (classify → escalate) that any future failure class can plug into.

### 9.5 Open, undecided as of this writing

- **Classification confidence threshold / allow-deny list** for what counts as "flagged" — `classification_min_confidence`, `classification_allow`/`deny` on `PictureDescriptionBaseOptions` exist and can gate this, but no threshold has been chosen or tested.
- **Gemini prompt/output contract** — free-text description vs. constrained/structured output (e.g. forcing a closed label set for icon legends). Free text carries more hallucination risk; not yet decided.
- **Provenance metadata** — flagged as a planned field in Section 6's output contract table but not yet implemented: the exact schema (method tag values, link format back to the stored picture crop) still needs to be designed.
- **Multi-panel reading order is not addressed by this direction** (see 9.4) — the Gemini-extraction path targets symbolic content; multi-panel reading order remains an accepted, undecided-on gap unless revisited separately.
