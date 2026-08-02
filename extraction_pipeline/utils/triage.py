"""Picture triage — Section 9.4 of the approach doc.

Decides which PictureItems are worth escalating to Gemini, using Docling's
own in-process picture classifier (already run as part of convert(), no
second pass). Schema confirmed directly against the installed Docling
version's DocumentPictureClassifier (docling.models.stages.picture_classifier):
classification lands on `picture.meta.classification.predictions`, each a
PictureClassificationPrediction(class_name, confidence, created_by) —
not the draft field names in the approach doc's earlier revisions.
"""

from dataclasses import dataclass

from docling_core.types.doc.document import DoclingDocument, PictureItem

from extraction_pipeline.utils.config import TriageConfig


@dataclass(frozen=True)
class TriageResult:
    picture: PictureItem
    flagged: bool
    top_class: str | None
    top_confidence: float | None
    reason: str


def needs_gemini_extraction(picture: PictureItem, config: TriageConfig) -> TriageResult:
    """Fail-open router: no classifier signal escalates rather than silently
    skipping (Section 9.4). Otherwise flags everything except configured
    noise labels (logos, signatures, QR/bar codes, stamps, thumbnails) —
    see config.py's NOISE_LABELS comment for why the net is cast this wide
    with no real corpus yet to tune against."""
    classification = picture.meta.classification if picture.meta else None
    predictions = classification.predictions if classification else None

    if not predictions:
        return TriageResult(
            picture=picture,
            flagged=True,
            top_class=None,
            top_confidence=None,
            reason="no classifier signal — fail open",
        )

    top = max(predictions, key=lambda p: p.confidence)

    if top.class_name in config.noise_labels:
        return TriageResult(
            picture=picture,
            flagged=False,
            top_class=top.class_name,
            top_confidence=top.confidence,
            reason=f"noise label '{top.class_name}'",
        )

    if top.confidence < config.min_confidence:
        return TriageResult(
            picture=picture,
            flagged=False,
            top_class=top.class_name,
            top_confidence=top.confidence,
            reason=f"below min_confidence ({top.confidence:.2f} < {config.min_confidence:.2f})",
        )

    return TriageResult(
        picture=picture,
        flagged=True,
        top_class=top.class_name,
        top_confidence=top.confidence,
        reason=f"flagged: '{top.class_name}' ({top.confidence:.2f})",
    )


def triage_pictures(doc: DoclingDocument, config: TriageConfig) -> list[TriageResult]:
    return [needs_gemini_extraction(picture, config) for picture in doc.pictures]
