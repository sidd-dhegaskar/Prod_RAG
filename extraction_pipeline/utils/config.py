"""Central configuration for the extraction pipeline.

Values here mirror Documents/EXTRACTION_APPROACH.md Section 3 (config
decisions) and Section 2 (tool choice). Kept as one module so every stage
reads settings from a single place instead of hardcoding flags.
"""

from dataclasses import dataclass, field
from pathlib import Path

from docling.datamodel.base_models import InputFormat

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = PIPELINE_ROOT / "samples"
OUTPUT_DIR = PIPELINE_ROOT / "output"
REPORTS_DIR = OUTPUT_DIR / "reports"
CONTENT_DIR = OUTPUT_DIR / "content"

# Section 3: explicit allowed_formats whitelist — the actual mechanism for
# "support all kinds of data types" (confirmed via the run_with_formats example).
DEFAULT_ALLOWED_FORMATS = [
    InputFormat.PDF,
    InputFormat.IMAGE,
    InputFormat.DOCX,
    InputFormat.HTML,
    InputFormat.PPTX,
    InputFormat.CSV,
    InputFormat.MD,
]

# Section 9.4 triage labels, confirmed against the installed Docling version's
# actual PictureClassificationLabel enum (docling_core.types.doc.labels) —
# broader than the approach doc's illustrative list. Per-call decision (not
# yet corpus-tuned, see Section 4/9.7): only skip picture classes that are
# confidently non-informational on their own (branding/auth marks, not
# content). Everything else — including photograph/screenshot/other — is
# flagged for Gemini escalation, since there's no real corpus yet to justify
# excluding them.
NOISE_LABELS = {
    "logo",
    "signature",
    "qr_code",
    "bar_code",
    "stamp",
    "page_thumbnail",
}

# Fail-open default: no classifier signal at all still routes to Gemini
# (Section 9.4) rather than silently skipping a picture.
DEFAULT_MIN_CONFIDENCE = 0.0


@dataclass(frozen=True)
class ExtractionConfig:
    """Converter/pipeline settings. Defaults match the approach doc's
    Section 3 decisions; override per-call for experimentation, not by
    editing these defaults in place."""

    do_table_structure: bool = True
    table_mode_accurate: bool = True  # ACCURATE vs FAST — Section 3
    do_cell_matching: bool = True
    force_full_page_ocr: bool = True  # dominant driver of OCR latency — accepted tradeoff, Section 3
    generate_picture_images: bool = True  # required for picture.get_image(doc) during triage/Gemini prep
    do_picture_classification: bool = True  # required for triage routing (Section 9.4)
    images_scale: float = 2.0
    allowed_formats: list = field(default_factory=lambda: list(DEFAULT_ALLOWED_FORMATS))


@dataclass(frozen=True)
class TriageConfig:
    """Routing thresholds for Section 9.4's needs_gemini_extraction().
    Starting values, not corpus-tuned — see NOISE_LABELS comment above."""

    noise_labels: frozenset = field(default_factory=lambda: frozenset(NOISE_LABELS))
    min_confidence: float = DEFAULT_MIN_CONFIDENCE
