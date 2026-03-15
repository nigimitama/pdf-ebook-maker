"""PDF builder — assembles images (and optional OCR text layer) into a PDF file."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from .font_resolver import resolve_ocr_font

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
    fit_page: bool = True,
    ocr_results: dict[str, list] | None = None,
) -> None:
    """Build a PDF from image_paths, embedding an invisible OCR text layer when provided.

    Parameters
    ----------
    image_paths:  Ordered list of image file paths.
    output_path:  Destination .pdf file path (including filename).
    fit_page:     Scale each image to fit an A4 page when True.
    ocr_results:  Mapping of image path → list[OcrResult]; None to skip OCR layer.
    """
    from reportlab.lib.pagesizes import A4  # noqa: PLC0415
    from reportlab.pdfgen import canvas as rl_canvas  # noqa: PLC0415

    _ocr = ocr_results or {}
    c = rl_canvas.Canvas(output_path)

    for path in image_paths:
        pil_img = Image.open(path).convert("RGB")
        img_w, img_h = pil_img.size
        page_w, page_h = A4 if fit_page else (float(img_w), float(img_h))

        c.setPageSize((page_w, page_h))
        scale_x = page_w / img_w
        scale_y = page_h / img_h

        c.drawInlineImage(pil_img, 0, 0, width=page_w, height=page_h)
        _embed_ocr_layer(c, _ocr.get(path, []), scale_x, scale_y, page_h)
        c.showPage()

    c.save()


def _embed_ocr_layer(c, results: list, scale_x: float, scale_y: float, page_h: float) -> None:
    """Draw invisible OCR text over the current canvas page (PDF spec §9.3.6)."""
    for r in results:
        x, y, w, h = r.bbox
        pdf_x = x * scale_x
        pdf_y = page_h - (y + h) * scale_y  # reportlab Y-axis is bottom-up
        font_size = max(4, int(h * scale_y * 0.9))
        tx = c.beginText(pdf_x, pdf_y)
        tx.setTextRenderMode(3)  # 3 = invisible
        tx.setFont(resolve_ocr_font(), font_size)
        tx.textLine(r.text)
        c.drawText(tx)
