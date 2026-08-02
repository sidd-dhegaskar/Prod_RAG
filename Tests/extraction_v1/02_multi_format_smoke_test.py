"""Validation plan Step 2 — multi-format smoke test.

Confirms one sample file per format (PDF, DOCX, PPTX, HTML, image, CSV, MD)
converts without error under the allowed_formats whitelist. Validates
format coverage, not table fidelity.

Usage: python 02_multi_format_smoke_test.py
Drops all files to test into samples/ (any mix of supported extensions).
"""

from pathlib import Path

from common import build_converter, report_writer, save_document_content

SAMPLES_DIR = Path(__file__).parent / "samples"

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".html", ".htm",
    ".png", ".jpg", ".jpeg", ".tiff", ".bmp",
    ".csv", ".md",
}


def main():
    files = [
        f for f in SAMPLES_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    if not files:
        print(f"No sample files found in {SAMPLES_DIR}")
        print(f"Drop one file per format to test: {sorted(SUPPORTED_EXTENSIONS)}")
        return

    converter = build_converter()
    results = []

    for f in files:
        try:
            result = converter.convert(f)
            save_document_content(result.document, f.stem)
            results.append((f.name, "OK", str(result.status)))
        except Exception as e:
            results.append((f.name, "FAIL", str(e)))

    with report_writer("02_multi_format_smoke_test") as (emit, report_path):
        emit(f"{'File':<40} {'Result':<8} Detail")
        emit("-" * 80)
        for name, outcome, detail in results:
            emit(f"{name:<40} {outcome:<8} {detail}")

        failures = [r for r in results if r[1] == "FAIL"]
        if failures:
            emit(f"\n{len(failures)}/{len(results)} failed.")
        else:
            emit(f"\nAll {len(results)} sample files converted successfully.")

    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    main()
