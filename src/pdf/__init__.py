"""PDF generation — image-to-PDF builder with optional invisible OCR text layer."""

from .builder import SUPPORTED_EXTS, build_pdf, collect_image_paths

__all__ = ["SUPPORTED_EXTS", "build_pdf", "collect_image_paths"]
