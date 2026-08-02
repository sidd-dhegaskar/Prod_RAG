"""Tests panel_reconstruction.py against real picture content from a
converted document. Prints original (raw Docling) order vs. reconstructed
(title-anchored) order for every picture in the document, so both can be
compared directly.

Usage: python 07_test_panel_reconstruction.py <path-to-pdf>
"""

import sys
from pathlib import Path

from common import build_converter, report_writer
from panel_reconstruction import Item, reconstruct, render


def picture_items(doc, picture) -> list[Item]:
    items = []
    for child in picture.children:
        ref = child.resolve(doc)
        if not getattr(ref, "text", None) or not ref.prov:
            continue
        bbox = ref.prov[0].bbox
        items.append(Item(text=ref.text, l=bbox.l, t=bbox.t, r=bbox.r, b=bbox.b))
    return items


def main():
    if len(sys.argv) != 2:
        print("Usage: python 07_test_panel_reconstruction.py <path-to-pdf>")
        sys.exit(1)

    doc_path = Path(sys.argv[1])
    converter = build_converter()
    result = converter.convert(doc_path)
    doc = result.document

    with report_writer("07_test_panel_reconstruction") as (emit, report_path):
        emit(f"Document: {doc_path.name}")
        emit(f"Pictures: {len(doc.pictures)}\n")

        for i, picture in enumerate(doc.pictures):
            items = picture_items(doc, picture)
            if not items:
                continue

            page_no = picture.prov[0].page_no if picture.prov else "?"
            panels = reconstruct(items)

            emit(f"=== Picture {i} (page {page_no}, {len(items)} text items, {len(panels)} panel(s) detected) ===")

            emit("--- RAW (Docling reading order) ---")
            raw_order = sorted(items, key=lambda it: (-it.t, it.l))
            emit(" | ".join(it.text for it in raw_order[:12]) + (" ..." if len(raw_order) > 12 else ""))

            emit("--- RECONSTRUCTED (title-anchored) ---")
            emit(render(panels))
            emit("")

    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    main()
