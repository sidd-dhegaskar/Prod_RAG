"""Validation plan Step 5 — batch run.

Runs the full sample set through convert_all(raises_on_error=False) so a
failure on one document doesn't block seeing results for the rest; prints
a summary of successes/failures at the end.

Usage: python 04_batch_convert.py
"""

from pathlib import Path

from common import build_converter, report_writer, save_document_content

SAMPLES_DIR = Path(__file__).parent / "samples"


def main():
    files = [f for f in SAMPLES_DIR.iterdir() if f.is_file()]

    if not files:
        print(f"No sample files found in {SAMPLES_DIR}")
        return

    converter = build_converter()
    conv_results = converter.convert_all(files, raises_on_error=False)

    ok, failed = [], []
    for res in conv_results:
        if str(res.status).endswith("SUCCESS"):
            save_document_content(res.document, res.input.file.stem)
            ok.append(res)
        else:
            failed.append(res)

    with report_writer("04_batch_convert") as (emit, report_path):
        emit(f"Converted: {len(ok)}/{len(files)}")
        for res in ok:
            n_tables = len(res.document.tables)
            emit(f"  OK   {res.input.file.name} ({n_tables} table(s))")

        if failed:
            emit(f"\nFailed: {len(failed)}")
            for res in failed:
                emit(f"  FAIL {res.input.file.name} — status: {res.status}")
                for err in getattr(res, "errors", []):
                    emit(f"       {err}")

    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    main()
