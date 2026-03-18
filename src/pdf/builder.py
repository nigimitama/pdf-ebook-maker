"""PDF builder — assembles images (and optional OCR text layer) into a PDF file."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

from .font_resolver import resolve_ocr_font

if TYPE_CHECKING:
    from document_structure import TocEntry

SUPPORTED_EXTS: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}
)


def collect_image_paths(sources: list[str], *, sort_by_name: bool = False) -> list[str]:
    """Expand a list of file/folder paths into a flat, ordered list of image file paths."""
    paths: list[str] = []
    for src in sources:
        p = Path(src)
        if p.is_dir():
            paths.extend(
                str(f) for f in p.iterdir()
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS
            )
        elif p.suffix.lower() in SUPPORTED_EXTS:
            paths.append(str(p))
    if sort_by_name:
        paths.sort(key=lambda x: Path(x).name.lower())
    return paths


def build_pdf(
    image_paths: list[str],
    output_path: str,
    *,
    ocr_results: dict[str, list] | None = None,
    toc_entries: list[TocEntry] | None = None,
    contrast_adjust: bool = False,
    brightness: int = 20,
    gamma: float = 1.6,
    resize_width: int | None = None,
    resize_height: int | None = None,
) -> None:
    """Build a PDF from image_paths, embedding an invisible OCR text layer when provided.

    Parameters
    ----------
    image_paths:     Ordered list of image file paths.
    output_path:     Destination .pdf file path (including filename).
    ocr_results:     Mapping of image path → list[OcrResult]; None to skip OCR layer.
    toc_entries:     TOC entries used to embed PDF outline bookmarks; None to skip.
    contrast_adjust: Apply gamma + brightness correction before embedding images.
    brightness:      Additive brightness offset (used when contrast_adjust=True).
    gamma:           Gamma correction value (used when contrast_adjust=True).
    resize_width:    Target width in px; height scales proportionally (None = disabled).
    resize_height:   Target height in px; width scales proportionally (None = disabled).
    """
    from reportlab.pdfgen import canvas as rl_canvas  # noqa: PLC0415

    _ocr = ocr_results or {}
    _toc_index = _build_toc_index(toc_entries or [])

    c = rl_canvas.Canvas(output_path)

    for page_num, path in enumerate(image_paths):
        pil_img = Image.open(path).convert("RGB")
        if resize_width or resize_height:
            pil_img = _apply_resize(pil_img, target_width=resize_width, target_height=resize_height)
        if contrast_adjust:
            pil_img = _apply_contrast(pil_img, brightness=brightness, gamma=gamma)
        img_w, img_h = pil_img.size
        page_w, page_h = (float(img_w), float(img_h))

        c.setPageSize((page_w, page_h))
        scale_x = page_w / img_w
        scale_y = page_h / img_h

        c.drawInlineImage(pil_img, 0, 0, width=page_w, height=page_h)
        _embed_ocr_layer(c, _ocr.get(path, []), scale_x, scale_y, page_h)
        _embed_toc_bookmarks(c, _toc_index.get(page_num, []), page_h)
        c.showPage()

    c.save()


def _build_toc_index(toc_entries: list[TocEntry]) -> dict[int, list[TocEntry]]:
    """Group TocEntry objects by page_index for O(1) lookup per page."""
    index: dict[int, list[TocEntry]] = {}
    for entry in toc_entries:
        index.setdefault(entry.page_index, []).append(entry)
    return index


def _embed_toc_bookmarks(c, entries: list[TocEntry], page_h: float) -> None:
    """Add ReportLab PDF outline (bookmark) entries for this page."""
    for entry in entries:
        key = f"toc_{id(entry)}"
        c.bookmarkPage(key, fit="FitH", top=page_h)
        c.addOutlineEntry(entry.title, key, level=entry.level - 1, closed=False)


def _apply_resize(img: Image.Image, *, target_width: int | None, target_height: int | None) -> Image.Image:
    """Resize image via image_processing.resize_image (aspect-ratio preserving)."""
    from image_processing import resize_image  # noqa: PLC0415
    arr = resize_image(np.array(img), target_width=target_width, target_height=target_height)
    return Image.fromarray(arr)


def _apply_contrast(img: Image.Image, *, brightness: int, gamma: float) -> Image.Image:
    """Apply gamma + brightness correction via image_processing.transform_intensity."""
    from image_processing import transform_intensity  # noqa: PLC0415
    arr = transform_intensity(np.array(img), brightness=brightness, gamma=gamma)
    return Image.fromarray(arr)


def _embed_ocr_layer(c, results: list, scale_x: float, scale_y: float, page_h: float) -> None:
    """Draw invisible OCR text over the current canvas page (PDF spec §9.3.6)."""
    font_name = resolve_ocr_font()
    for r in results:
        if not r.text:
            continue
        x, y, w, h = r.bbox
        bbox_w = w * scale_x
        bbox_h = h * scale_y
        pdf_x = x * scale_x
        pdf_y = page_h - (y + h) * scale_y  # reportlab Y-axis is bottom-up

        if r.is_vertical:
            font_size = max(4.0, bbox_w)
            span = bbox_h
        else:
            font_size = max(4.0, bbox_h)
            span = bbox_w

        natural_w = c.stringWidth(r.text, font_name, font_size)
        horiz_scale = (span / natural_w * 100.0) if natural_w > 0 else 100.0

        tx = c.beginText(pdf_x, pdf_y)
        tx.setTextRenderMode(3)  # 3 = invisible
        tx.setFont(font_name, font_size)
        tx.setHorizScale(horiz_scale)
        tx.textLine(r.text)
        c.drawText(tx)
