"""Reassembles each picture region from the extracted (text, bbox) data and
renders it next to the original cropped image, so extraction quality can be
checked visually instead of by reading raw JSON.

For each picture in the document, produces one PNG with three panels:
  1. Original cropped image (what Docling/OCR actually saw)
  2. Overlay: original image + bounding boxes + extracted text drawn on top
  3. Reconstructed: blank canvas, text laid out via panel_reconstruction.py
     (title-anchored panel grouping), so you can see the corrected reading
     order independent of the original image.

Usage: python 08_visualize_extraction.py <path-to-pdf>
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


def to_local_pixels(item: Item, pic_bbox, scale: float):
    """Converts a page-coordinate bbox (BOTTOMLEFT origin) into pixel
    coordinates local to the picture's own cropped image (TOP-LEFT origin)."""
    x0 = (item.l - pic_bbox.l) * scale
    x1 = (item.r - pic_bbox.l) * scale
    y0 = (pic_bbox.t - item.t) * scale
    y1 = (pic_bbox.t - item.b) * scale
    return x0, y0, x1, y1


def render_overlay(base_image: Image.Image, items: list[Item], pic_bbox, scale: float) -> Image.Image:
    overlay = base_image.convert("RGB").copy()
    draw = ImageDraw.Draw(overlay)
    font = load_font(11)

    for item in items:
        x0, y0, x1, y1 = to_local_pixels(item, pic_bbox, scale)
        draw.rectangle([x0, y0, x1, y1], outline="red", width=1)
        draw.text((x0, max(0, y0 - 12)), item.text[:30], fill="blue", font=font)

    return overlay


def render_reconstructed(items: list[Item], width: int) -> Image.Image:
    panels = reconstruct(items)
    font = load_font(13)
    line_height = 18
    lines = []
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
        print("Usage: python 08_visualize_extraction.py <path-to-pdf>")
        sys.exit(1)

    doc_path = Path(sys.argv[1])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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

        pic_bbox = picture.prov[0].bbox
        overlay = render_overlay(base_image, items, pic_bbox, IMAGES_SCALE)
        reconstructed = render_reconstructed(items, width=base_image.width)

        composite = stack_horizontal([base_image.convert("RGB"), overlay, reconstructed])
        out_path = OUTPUT_DIR / f"{doc_path.stem}-picture-{i}.png"
        composite.save(out_path)
        saved.append(out_path)
        print(f"Picture {i} (page {picture.prov[0].page_no}, {len(items)} items) -> {out_path}")

    if not saved:
        print("No pictures with extractable text found.")
    else:
        print(f"\n{len(saved)} visualization(s) saved to {OUTPUT_DIR}")
        print("Panel order in each image: [original crop] [bbox+text overlay] [reconstructed reading order]")


if __name__ == "__main__":
    main()
