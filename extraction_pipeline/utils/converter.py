"""Docling DocumentConverter builder for the extraction pipeline.

Implements Documents/EXTRACTION_APPROACH.md Sections 2-3: Docling + RapidOCR,
TableFormer in ACCURATE mode with cell matching, full-page OCR, and the
explicit allowed_formats whitelist. This is the only place the pipeline
constructs a DocumentConverter.
"""

from docling.datamodel.image_classification_engine_options import (
    TransformersImageClassificationEngineOptions,
)
from docling.datamodel.picture_classification_options import (
    DocumentPictureClassifierOptions,
)
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    RapidOcrOptions,
    TableFormerMode,
    TableStructureOptions,
)
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter, PdfFormatOption

from extraction_pipeline.utils.config import ExtractionConfig


def build_converter(config: ExtractionConfig | None = None) -> DocumentConverter:
    """Builds a DocumentConverter wired per the approach doc's config decisions.

    RapidOCR is used as the OCR backend (Section 2): this Docling version has
    no native PaddleOCR options class — only EasyOcrOptions, TesseractOcrOptions,
    RapidOcrOptions, OcrMacOptions, KserveV2OcrOptions, NemotronOcrOptions exist.
    RapidOCR runs PaddleOCR's own detection/recognition models via ONNX runtime,
    so it's the closest first-class equivalent.
    """
    config = config or ExtractionConfig()

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = config.do_table_structure
    pipeline_options.table_structure_options = TableStructureOptions(
        mode=TableFormerMode.ACCURATE if config.table_mode_accurate else TableFormerMode.FAST,
        do_cell_matching=config.do_cell_matching,
    )
    # Docling's default only OCRs pages with no digital text layer, which
    # starves text baked into pictures/graphics on otherwise digital-native
    # pages. force_full_page_ocr re-OCRs every page as a full image instead —
    # the dominant driver of OCR latency, an accepted completeness-over-speed
    # tradeoff (Section 3).
    pipeline_options.ocr_options = RapidOcrOptions(force_full_page_ocr=config.force_full_page_ocr)
    pipeline_options.do_picture_classification = config.do_picture_classification
    # Docling's default (default_compile_model() -> True) runs the picture
    # classifier through torch.compile(), which needs a working C++ toolchain
    # (MSVC's cl.exe on Windows) at first-call time. Not available/assumed in
    # this environment, so it's disabled explicitly here rather than left to
    # the ambient default — a supported config option, not a workaround.
    pipeline_options.picture_classification_options = DocumentPictureClassifierOptions(
        engine_options=TransformersImageClassificationEngineOptions(compile_model=False),
    )
    # Needed for PictureItem.get_image(doc) during triage (Section 9.4/9.5).
    pipeline_options.generate_picture_images = config.generate_picture_images
    pipeline_options.images_scale = config.images_scale

    return DocumentConverter(
        allowed_formats=config.allowed_formats,
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        },
    )
