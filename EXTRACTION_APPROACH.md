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
| OCR engine | PaddleOCR | Confirm plugin API for the pinned Docling version — the OCR-backend interface has changed across releases. |
| OCR scope | On-demand (default) | Runs PaddleOCR only on pages without a text layer, not full-page OCR on every page. Cheaper and correct for a mixed digital/scanned corpus. |
| Output format | **HTML** (or raw `DoclingDocument` JSON) for any document containing tables | Markdown cannot represent merged/spanned cells — exporting to Markdown would silently destroy the table structure TableFormer just extracted. Markdown is acceptable only for table-free content. |

## 4. Open questions

- What fraction of the source corpus is scanned/image-based vs. digital-native? Determines how much PaddleOCR tuning effort is worth investing now vs. later.
- Which Docling version are we pinning to, and does its OCR plugin API support PaddleOCR directly, or does it require a custom OCR backend wrapper?
- Do we have representative "hard" documents (merged headers, nested tables, scanned tables) to validate against before this is trusted in the pipeline?

## 5. Validation plan

Before this extraction step is considered ready to feed downstream work:

1. Collect 3–5 representative documents with the gnarliest real tables in the corpus (merged headers, nested tables, and — if available — scanned tables).
2. Run extraction with the config above; export to HTML.
3. Manually inspect each table's HTML output against the source document for structural correctness (cell merges, header association, row/column order).
4. Note failure patterns (if any) and decide whether they need `ACCURATE`-mode tuning, a different OCR engine, or manual post-processing rules.

## 6. Explicitly out of scope here

- Chunking strategy for tables (keeping header+rows atomic through the splitter) — deferred to the chunking phase.
- ACL/metadata tagging.
- Non-document sources (audio/video transcription, structured data/API connectors).
- Embedding, indexing, retrieval.
