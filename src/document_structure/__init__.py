"""document_structure — models and auto-detection for document page structure."""

from .detector import build_structure, parse_toc_line
from .models import DocumentStructure, PageCategory, PageEntry, TocEntry, category_label

__all__ = [
    "DocumentStructure",
    "PageCategory",
    "PageEntry",
    "TocEntry",
    "build_structure",
    "category_label",
    "parse_toc_line",
]
