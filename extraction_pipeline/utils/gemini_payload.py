"""Gemini request payload assembly — Section 9.5 of the approach doc.

Builds everything needed to call Gemini for a flagged picture (image bytes,
structured-output response schema, prompt, provenance for writing the result
back per Section 9.6) without making the API call itself. No google-genai
dependency here — that's the next stage, once these payloads are validated
against real samples.
"""

import base64
import io
from dataclasses import dataclass, field

from docling_core.types.doc.document import DoclingDocument, PictureItem
from PIL import Image

# Draft schema per Section 9.5 — starting point, to be refined against real
# samples (multi-panel charts, icon-legend tables), not final.
GEMINI_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "content_type": {
            "type": "string",
            "enum": ["table", "chart", "icon_legend_table", "other"],
        },
        "title": {"type": "string"},
        "extracted_text": {"type": "string"},  # used when content_type == "other"
        "table_rows": {  # used when content_type in {"table", "icon_legend_table"}
            "type": "array",
            "items": {"type": "array", "items": {"type": "string"}},
        },
        "notes": {"type": "string"},  # model's own caveats — informational only
    },
    "required": ["content_type"],
}

GEMINI_PROMPT = (
    "Extract the complete content of this image from a document. "
    "If it is a table or a chart/legend that encodes values using icons or "
    "symbols instead of (or in addition to) text, capture every row and "
    "column faithfully, including symbolic values (e.g. an up-arrow, a dash, "
    "'n.a.') as literal text in the corresponding cell rather than omitting "
    "them. Respond only in the given structured schema — do not narrate or "
    "add commentary outside the schema fields."
)


@dataclass(frozen=True)
class GeminiRequestPayload:
    """Everything needed to call Gemini for one flagged picture, plus the
    provenance needed to write the result back onto the right PictureItem
    per Section 9.6 (picture_ref identifies which element to update)."""

    picture_ref: str  # picture.self_ref — round-trips back to the PictureItem
    page_no: int | None
    top_class: str | None
    top_confidence: float | None
    image_bytes: bytes
    image_mime_type: str
    image_base64: str
    prompt: str = GEMINI_PROMPT
    response_schema: dict = field(default_factory=lambda: GEMINI_RESPONSE_SCHEMA)


def build_gemini_payload(
    picture: PictureItem,
    doc: DoclingDocument,
    top_class: str | None = None,
    top_confidence: float | None = None,
) -> GeminiRequestPayload | None:
    """Crops the picture from the document and assembles the Gemini request
    payload. Returns None if the image isn't available (generate_picture_images
    was off during conversion, or the crop failed) rather than raising —
    the caller decides how to handle a picture it can't build a payload for."""
    image: Image.Image | None = picture.get_image(doc)
    if image is None:
        return None

    buf = io.BytesIO()
    image_rgb = image.convert("RGB")
    image_rgb.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    page_no = picture.prov[0].page_no if picture.prov else None

    return GeminiRequestPayload(
        picture_ref=picture.self_ref,
        page_no=page_no,
        top_class=top_class,
        top_confidence=top_confidence,
        image_bytes=image_bytes,
        image_mime_type="image/png",
        image_base64=base64.b64encode(image_bytes).decode("ascii"),
    )
