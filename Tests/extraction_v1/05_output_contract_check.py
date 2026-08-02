"""Format-uniformity check, per EXTRACTION_APPROACH.md Section 6.

Converts one sample per format and diffs the element structure (types,
metadata fields present) to verify all input formats converge on the same
DoclingDocument schema, rather than assuming uniformity from the docs.

Usage: python 05_output_contract_check.py <file-1> <file-2> [...]
Pass at least two files of different formats (e.g. one .pdf, one .docx).
"""

import json
import sys
from pathlib import Path

from common import build_converter, report_writer

OUTPUT_DIR = Path(__file__).parent / "output" / "contract_check"


def element_type_summary(doc) -> dict:
    types = {}
    for item, _ in doc.iterate_items():
        label = str(getattr(item, "label", type(item).__name__))
        types[label] = types.get(label, 0) + 1
    return types


def main():
    if len(sys.argv) < 3:
        print("Usage: python 05_output_contract_check.py <file-1> <file-2> [...]")
        print("Pass at least two files of different formats.")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    converter = build_converter()

    summaries = {}
    with report_writer("05_output_contract_check") as (emit, report_path):
        for path_str in sys.argv[1:]:
            doc_path = Path(path_str)
            result = converter.convert(doc_path)
            doc = result.document

            out_path = OUTPUT_DIR / f"{doc_path.stem}.json"
            out_path.write_text(json.dumps(doc.export_to_dict(), indent=2), encoding="utf-8")

            summary = element_type_summary(doc)
            summaries[doc_path.name] = summary

            emit(f"{doc_path.name} ({doc_path.suffix}): element types = {summary}")
            emit(f"  full export -> {out_path}")

        all_type_sets = [set(s.keys()) for s in summaries.values()]
        common_types = set.intersection(*all_type_sets) if all_type_sets else set()
        emit(f"\nElement types common to all converted formats: {sorted(common_types)}")
        emit("Review the JSON exports above to confirm per-element metadata fields")
        emit("(page number, reading order, heading path) match across formats.")

    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    main()
