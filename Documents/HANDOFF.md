# Handoff — Extraction Pipeline Investigation

Written to resume this work in a new conversation. Read this, then
`Documents/EXTRACTION_APPROACH.md` for the full config rationale.

## Where this sits in the bigger picture

This is all Layer 1 (Ingestion & preprocessing) of `Documents/RAG_SYSTEM_DESIGN.md`
— specifically the **extraction** sub-step only. Chunking, ACL tagging,
embedding, retrieval: none of that has been started.

## What exists and works

- `.venv/` + root `requirements.txt` (docling, pandas, tabulate) — set up, installed, working.
- `Tests/extraction_v1/` — a working test harness against **Docling** (parser)
  + **RapidOCR** (OCR engine — see "PaddleOCR" note below).
  - `common.py` — shared `build_converter()` + `save_document_content()` + `report_writer()`.
  - `01`–`06` — validation scripts (single-doc check, multi-format smoke test,
    table export, batch run, output-contract check, OCR-completeness comparison).
  - `panel_reconstruction.py` + `07` — title-anchored panel reordering (see below).
  - `08_visualize_extraction.py` — renders `[original picture crop] | [bbox+text overlay] | [reconstructed text]`
    side by side as a PNG. **This is the most useful debugging tool built so far** — use it
    first on any new document before writing more code.
  - `samples/` has two real test PDFs already in place: `022-article-A002-en.pdf`
    (stock-market article, chart-heavy) and `test_pdf.pdf` (system-design doc, real tables + diagrams).

- **PaddleOCR resolved**: this Docling version has no native PaddleOCR options
  class. We use **RapidOCR** instead — it runs PaddleOCR's own detection/recognition
  models via ONNX runtime, so it's the closest available equivalent.

- **Two real bugs found and fixed** (both now defaults in `common.py`):
  1. `force_full_page_ocr=True` — Docling's default only OCRs pages with no
     digital text layer, which starves picture-embedded text on otherwise
     digital-native pages. Confirmed via `06_compare_full_page_ocr.py`: default
     config missed labels like "Very developed"; full-page OCR recovered them.
  2. `export_to_markdown(traverse_pictures=True)` — the markdown export was
     silently dropping all picture-nested text regardless of OCR quality.
     This was actually the bigger fix (0/8 → 7/8 test fragments recovered
     from this alone, before the OCR fix added the last one).

## What's broken / unsolved

### 1. Reading order on multi-panel pictures (partially solved)
When a picture contains multiple independent panels (e.g. two charts side by
side), Docling/OCR reads them interleaved row-by-row instead of grouped by panel.

**Built:** `panel_reconstruction.py` — finds text matching `Chart N` / `Figure N`
/ `Table N` as anchors, assigns every other text item to its nearest anchor by
2D distance, groups and re-orders per panel.

**Confirmed working:** simple 2-panel side-by-side case (page 2 of the stock
market PDF) — correctly separated into two clean, complete panels.

**Confirmed broken:** genuine 2×2 grid (page 3 of the same PDF, 4 charts:
Chart 4/5/6/7) — nearest-anchor-by-raw-distance produces wrong groupings
(content bleeds across panels). Needs quadrant-aware assignment, not naive
nearest-neighbor. **Not yet fixed.**

### 2. Symbolic/iconographic content — NOT an OCR problem, unsolved
Found via `08_visualize_extraction.py` on page 4 of the stock-market PDF (a
table using up-arrow/dash/"n.a." icons to show trend direction per country).
Of ~38 icon cells, **only 1 was extracted at all, and it was wrong** (OCR
hallucinated a Chinese character `个` from an arrow glyph — also worth fixing
the OCR language default, currently `lang=['chinese']`, on an English corpus).

**Why this is different from bug #1**: this isn't a reading-order problem,
it's near-total data loss. Row/column labels (country names, years) survived;
the actual data (increase/decrease/n.a. per category) is gone. OCR cannot
recognize icons — they're not in its character set. No amount of OCR tuning
fixes this; it needs a different technique entirely.

## The real open strategic question (where the conversation left off)

Discussed but **not decided or built**: how to handle content OCR structurally
can't read (icons/symbols) or can't order (complex multi-panel layouts).

Key conclusions from that discussion, for whoever picks this up:

- **A full switch to "OCR text + VLM for all images" was considered and
  rejected as the default approach.** Reasons: VLMs are worse than OCR at
  precise character/number transcription (the opposite of what we need for
  most content, which OCR already handles fine); hallucination is a *worse*
  failure mode for RAG than missing data (silent vs. conspicuous); cost/latency
  multiply at corpus scale; it's a deviation from `RAG_SYSTEM_DESIGN.md`'s
  explicit self-hosted-stack architecture unless a self-hosted VLM is used.
- **Recommended direction instead (not yet built): a triage/confidence signal.**
  Keep OCR as the default for all pictures (fast, free, deterministic, proven
  to work for the majority case). Compute a cheap per-picture signal after
  extraction — e.g. extracted-text density relative to picture size/complexity,
  or RapidOCR's own `text_score` — to flag pictures that likely lost content.
  Only route *flagged* pictures to a VLM fallback, with structured/constrained
  output to limit hallucination risk, rather than blanket-routing everything.
- **Frontier labs (Google/Anthropic/OpenAI) do NOT "get every image correct"**
  — this was a corrected premise, not confirmed. Published benchmarks
  (ChartQA, DocVQA) show real, non-trivial error rates even for SOTA models on
  dense tables/complex charts. What they actually do differently: train
  vision+language jointly end-to-end (not OCR + hand-written heuristics bolted
  on after, which is what we've been building), so they generalize across
  document families where our hand-tuned thresholds (documented in
  `EXTRACTION_APPROACH.md` Section 8) explicitly don't.
- **How they audit at scale, for reference**: golden sets with human-verified
  ground truth re-run on every pipeline change (this is literally what
  `RAG_SYSTEM_DESIGN.md` Layer 6 already scoped — Ragas/DeepEval golden-set CI
  gate — just not yet applied specifically to extraction), sampled human
  review (not exhaustive), cross-validation/ensembling between methods,
  confidence-based routing, and downstream-task metrics as an indirect signal.

**Last message before this handoff was requested:** explicitly deferred
building a golden-set test harness, on the reasoning "no use building a test
if we don't have a pipeline we need to test for" — i.e. the triage/audit
layer is a real next step, but only once there's a settled pipeline shape to
audit, not before.

## Immediate next decision (pick up here)

Two live forks, not yet chosen between:
1. Fix the 2×2 grid case in `panel_reconstruction.py` (quadrant-aware anchor
   assignment instead of naive nearest-distance) — finishes bug #1.
2. Scope the triage/confidence-signal detector (bug #2's mitigation) — decide
   what "likely lost content" actually measures, and what the fallback does
   when a picture is flagged.

Neither has been started. Given the last message's reasoning, (2) probably
shouldn't be built as a *test* yet either — it needs to be a *production
signal design* decision first: what threshold, what fallback, is a VLM
dependency actually being added or not.

## Useful commands to resume

```
cd C:\Users\siddd\Desktop\Prod_RAG
.venv\Scripts\activate
python Tests/extraction_v1/08_visualize_extraction.py "Tests/extraction_v1/samples/022-article-A002-en.pdf"
```
Then look at `Tests/extraction_v1/output/visualizations/*.png` — fastest way
to re-orient on what's working vs. broken.
