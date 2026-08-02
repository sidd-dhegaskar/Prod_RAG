"""Stage 1 — OCR/table extraction + picture detection, triage, and Gemini
payload preparation (Section 9.1-9.5 of the approach doc).

Pipeline, one Docling conversion pass:
    convert() [OCR + table structure + picture classification, all in-process]
        -> doc.pictures: list[PictureItem], each already classified
        -> triage each picture (Section 9.4): flag chart/table/icon/etc.,
           skip noise labels (logo/signature/qr_code/bar_code/stamp/thumbnail)
        -> for flagged pictures, crop the image and assemble the exact
           Gemini request payload (image + schema + prompt) (Section 9.5)

This stage stops at "payload ready to send" — it does NOT call the Gemini
API and does NOT write anything back onto the document (that's Stage 2,
Section 9.6). No google-genai dependency, no API key required.

Usage:
    python -m extraction_pipeline.stage1_picture_triage.run_stage1 <path-to-document>
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

from extraction_pipeline.utils.config import CONTENT_DIR, ExtractionConfig, TriageConfig
from extraction_pipeline.utils.converter import build_converter
from extraction_pipeline.utils.gemini_payload import build_gemini_payload
from extraction_pipeline.utils.io import report_writer, save_document_content
from extraction_pipeline.utils.triage import triage_pictures


def run(source_path: Path) -> None:
    with report_writer("stage1") as (emit, report_path):
        emit(f"Stage 1 — converting: {source_path}")

        converter = build_converter(ExtractionConfig())
        result = converter.convert(str(source_path))
        doc = result.document

        emit(f"Status: {result.status}")
        emit(f"Pages: {len(doc.pages)}")
        emit(f"Tables detected: {len(doc.tables)}")
        emit(f"Pictures detected: {len(doc.pictures)}")

        triage_results = triage_pictures(doc, TriageConfig())

        payloads = []
        for tr in triage_results:
            status = "FLAGGED" if tr.flagged else "skipped"
            emit(f"  [{status}] {tr.picture.self_ref} — {tr.reason}")

            if not tr.flagged:
                continue

            payload = build_gemini_payload(
                tr.picture, doc, top_class=tr.top_class, top_confidence=tr.top_confidence
            )
            if payload is None:
                emit(f"    WARNING: no image available for {tr.picture.self_ref} — "
                     f"skipping payload (generate_picture_images may be off, or crop failed)")
                continue

            payloads.append(payload)

        emit(f"Gemini payloads prepared: {len(payloads)} / {len(triage_results)} pictures")

        # Save payloads (base64 image + schema + prompt) for inspection —
        # nothing here is sent to any API. image_bytes is dropped from the
        # serialized form since image_base64 already carries the same data
        # in a JSON-safe encoding.
        CONTENT_DIR.mkdir(parents=True, exist_ok=True)
        payloads_path = CONTENT_DIR / f"{source_path.stem}.gemini_payloads.json"
        serializable = [
            {k: v for k, v in asdict(p).items() if k != "image_bytes"} for p in payloads
        ]
        payloads_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
        emit(f"Gemini payloads written to: {payloads_path}")

        paths = save_document_content(doc, source_path.stem)
        emit(f"Markdown written to: {paths['markdown']}")
        emit(f"JSON written to: {paths['json']}")
        emit(f"Report written to: {report_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m extraction_pipeline.stage1_picture_triage.run_stage1 <path-to-document>")
        sys.exit(1)

    run(Path(sys.argv[1]))
