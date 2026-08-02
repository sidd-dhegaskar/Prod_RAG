"""Output/logging helpers for the extraction pipeline.

Keeps run output (stdout + a saved report) and converted-document content
(Markdown + full DoclingDocument JSON, per Section 6's output contract)
under extraction_pipeline/output/, isolated from Tests/extraction_v1/output/.
"""

import json
import sys
from contextlib import contextmanager
from datetime import datetime

from extraction_pipeline.utils.config import CONTENT_DIR, REPORTS_DIR


@contextmanager
def report_writer(script_name: str):
    """Writes every emit(...) call to both stdout and a timestamped report
    file under output/reports/, so run output is saved by default."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = REPORTS_DIR / f"{script_name}_{timestamp}.txt"

    with report_path.open("w", encoding="utf-8") as f:
        def emit(*args, sep=" ", end="\n"):
            text = sep.join(str(a) for a in args) + end
            sys.stdout.write(text)
            f.write(text)

        yield emit, report_path


def save_document_content(doc, stem: str) -> dict:
    """Saves extracted content for one converted document: Markdown for
    readability, full DoclingDocument JSON for the complete structured
    output (Section 6 output contract). Returns the paths written."""
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)

    md_path = CONTENT_DIR / f"{stem}.md"
    json_path = CONTENT_DIR / f"{stem}.json"

    md_path.write_text(doc.export_to_markdown(traverse_pictures=True), encoding="utf-8")
    json_path.write_text(json.dumps(doc.export_to_dict(), indent=2), encoding="utf-8")

    return {"markdown": md_path, "json": json_path}
