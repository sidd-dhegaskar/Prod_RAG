"""Renders PP-StructureV3's output next to the original picture crop and the
current RapidOCR + panel_reconstruction.py output, so the two approaches can
be compared visually on the same pictures instead of by reading raw JSON.

Background: PP-StructureV3 (PaddleOCR's layout+reading-order+table pipeline)
was probed as a candidate replacement for panel_reconstruction.py's
nearest-anchor heuristic, which fails on genuine multi-row/column grids (see
conversation). Confirmed via manual probe:
  - 2x2 chart grid (page 3 of 022-article-A002-en.pdf): PP-StructureV3
    correctly separates all 4 panels with no cross-panel bleed, vs. the
    heuristic's broken interleaving.
  - Icon/symbol table (page 4): PP-StructureV3 still fails, same as RapidOCR
    — confirms this is a distinct failure class (symbol vocabulary, not
    reading order) that no OCR-family engine addresses.

Requires: pip install paddlepaddle paddleocr "paddlex[ocr]"
Known environment issue: default PPStructureV3() init raises
NotImplementedError from Paddle's oneDNN backend on this machine
(Windows/CPU). Fixed by passing enable_mkldnn=False.

Usage: python 09_visualize_ppstructure.py <path-to-pdf>
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from common import build_converter
from panel_reconstruction import Item, reconstruct

OUTPUT_DIR = Path(__file__).parent / "output" / "visualizations"
IMAGES_SCALE = 2.0  # must match build_converter's pipeline_options.images_scale


def load_font(size: int):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def picture_items(doc, picture) -> list[Item]:
    items = []
    for child in picture.children:
        ref = child.resolve(doc)
        if not getattr(ref, "text", None) or not ref.prov:
            continue
        bbox = ref.prov[0].bbox
        items.append(Item(text=ref.text, l=bbox.l, t=bbox.t, r=bbox.r, b=bbox.b))
    return items


def render_reconstructed(items: list[Item], width: int) -> Image.Image:
    panels = reconstruct(items)
    font = load_font(13)
    line_height = 18
    lines = ["RapidOCR + panel_reconstruction.py:", ""]
    for panel in panels:
        for it in panel:
            lines.append(it.text)
        lines.append("─" * 40)

    height = max(100, line_height * (len(lines) + 1))
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    for i, line in enumerate(lines):
        draw.text((5, 5 + i * line_height), line, fill="black", font=font)
    return canvas


def render_ppstructure(crop_path: Path, width: int):
    """Runs PPStructureV3 on the saved crop and renders its parsing_res_list
    (already in reading order) as text blocks labeled by block type."""
    from paddleocr import PPStructureV3

    pipeline = PPStructureV3(enable_mkldnn=False)
    outputs = pipeline.predict(str(crop_path))
    res = outputs[0].json["res"]

    font = load_font(13)
    line_height = 16
    lines = ["PP-StructureV3:", ""]
    for block in res["parsing_res_list"]:
        label = block.get("block_label", "?")
        content = block.get("block_content", "")
        if not isinstance(content, str):
            content = str(content)
        lines.append(f"[{label}]")
        # wrap long content crudely by character count so it stays on-canvas
        wrap_width = max(20, width // 8)
        for start in range(0, len(content), wrap_width):
            lines.append(content[start:start + wrap_width])
        lines.append("─" * 40)

    height = max(100, line_height * (len(lines) + 1))
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    for i, line in enumerate(lines):
        draw.text((5, 5 + i * line_height), line, fill="black", font=font)
    return canvas


def stack_horizontal(images: list[Image.Image], gap: int = 10) -> Image.Image:
    height = max(im.height for im in images)
    total_width = sum(im.width for im in images) + gap * (len(images) - 1)
    canvas = Image.new("RGB", (total_width, height), "white")
    x = 0
    for im in images:
        canvas.paste(im, (x, 0))
        x += im.width + gap
    return canvas


def main():
    if len(sys.argv) != 2:
        print("Usage: python 09_visualize_ppstructure.py <path-to-pdf>")
        sys.exit(1)

    doc_path = Path(sys.argv[1])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    crops_dir = OUTPUT_DIR / "_crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    converter = build_converter(generate_picture_images=True)
    result = converter.convert(doc_path)
    doc = result.document

    saved = []
    for i, picture in enumerate(doc.pictures):
        items = picture_items(doc, picture)
        if not items or not picture.prov:
            continue

        base_image = picture.get_image(doc)
        if base_image is None:
            continue

        crop_path = crops_dir / f"{doc_path.stem}-picture-{i}.png"
        base_image.convert("RGB").save(crop_path)

        heuristic_panel = render_reconstructed(items, width=base_image.width)
        ppstructure_panel = render_ppstructure(crop_path, width=base_image.width)

        composite = stack_horizontal([
            base_image.convert("RGB"),
            heuristic_panel,
            ppstructure_panel,
        ])
        out_path = OUTPUT_DIR / f"{doc_path.stem}-picture-{i}-ppstructure-compare.png"
        composite.save(out_path)
        saved.append(out_path)
        print(f"Picture {i} (page {picture.prov[0].page_no}, {len(items)} items) -> {out_path}")

    if not saved:
        print("No pictures with extractable text found.")
    else:
        print(f"\n{len(saved)} comparison(s) saved to {OUTPUT_DIR}")
        print("Panel order in each image: [original crop] [RapidOCR + heuristic] [PP-StructureV3]")


if __name__ == "__main__":
    main()
