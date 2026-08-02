# extraction_pipeline

Isolated, self-contained implementation of the extraction stage described in
[`Documents/EXTRACTION_APPROACH.md`](../Documents/EXTRACTION_APPROACH.md).
Nothing in this folder imports from `Tests/extraction_v1/` and nothing
outside this folder should import from here — keep the pipeline self-contained.

## Layout

```
extraction_pipeline/
├── utils/                        # shared, reusable building blocks — nothing stage-specific
│   ├── config.py                 # ExtractionConfig, TriageConfig — all tunable settings in one place
│   ├── converter.py              # build_converter() — the Docling DocumentConverter builder
│   ├── io.py                     # report_writer(), save_document_content() — output helpers
│   ├── triage.py                 # needs_gemini_extraction() — Section 9.4 picture routing
│   └── gemini_payload.py         # build_gemini_payload() — Section 9.5 request assembly (no API call)
├── stage0_setup/                 # Stage 0 — scaffolding + basic converter smoke test
│   └── run_stage0.py
├── stage1_picture_triage/        # Stage 1 — OCR/tables + picture detection/triage + Gemini payload prep
│   └── run_stage1.py
├── samples/                      # put input documents here for local runs (gitignored content)
└── output/                       # generated — reports/ (run logs) and content/ (md + json + payloads per doc)
```

## Stages

- **Stage 0** (`stage0_setup/`) — environment/config scaffolding plus a
  working end-to-end conversion (text + table structure only, per Sections
  2-3 of the approach doc). No picture/Gemini extraction.
- **Stage 1** (`stage1_picture_triage/`) — one Docling conversion pass with
  picture classification enabled (Section 9.1-9.5): detects pictures, routes
  each through `needs_gemini_extraction()` (flags charts/tables/icons/etc.,
  skips logos/signatures/QR/bar codes/stamps/thumbnails), and for flagged
  pictures crops the image and assembles the exact Gemini request payload
  (image + structured-output schema + prompt). **Stops at "payload ready to
  send"** — does not call the Gemini API and does not write anything back
  onto the document yet. No `google-genai` dependency, no API key required.
- Later stages (multi-format smoke test, hard-table validation, batch runs,
  the actual Gemini API call, and writing results back per Section 9.6) get
  their own `stageN_*` folders as they're built, reusing the same `utils/`.

## Known environment note

Docling's picture classifier defaults to `torch.compile()` for the model
(`compile_model=True` by default), which needs a working C++ toolchain
(MSVC's `cl.exe` on Windows) the first time it runs. If that's not installed,
conversion fails inside `StandardPdfPipeline`. `utils/converter.py` disables
`compile_model` explicitly via `TransformersImageClassificationEngineOptions`
so this pipeline works without MSVC — a supported config option, not a patch
to Docling itself.

## Running

```
python -m extraction_pipeline.stage0_setup.run_stage0 <path-to-document>
python -m extraction_pipeline.stage1_picture_triage.run_stage1 <path-to-document>
```

Drop a sample document into `extraction_pipeline/samples/` and pass its path.
Output lands in `extraction_pipeline/output/reports/` (run log) and
`extraction_pipeline/output/content/` (`.md`, `.json`, and — for stage 1 —
`.gemini_payloads.json` per document).
