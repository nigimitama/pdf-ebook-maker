"""Font resolution for PDF generation — Unicode font with cross-platform fallbacks.

Priority:
    1. reportlab built-in CID font ``HeiseiKakuGo-W5`` — no external files required.
    2. Platform-specific system TTF/TTC font discovered at runtime.
    3. ``"Helvetica"`` — ASCII-only fallback, always available in PDF.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

# Preference-ordered Unicode font paths per platform
_SYSTEM_FONT_CANDIDATES: dict[str, list[str]] = {
    "win32": [
        "C:/Windows/Fonts/YuGothR.ttc",
        "C:/Windows/Fonts/YuGothM.ttc",
        "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
    ],
    "darwin": [
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/Library/Fonts/Arial Unicode MS.ttf",
    ],
    "linux": [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJKjp-Regular.otf",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
    ],
}


def _find_system_unicode_font() -> str | None:
    """Return the path of a Unicode-capable font on the current platform, or None."""
    key = sys.platform if sys.platform in _SYSTEM_FONT_CANDIDATES else "linux"
    for candidate in _SYSTEM_FONT_CANDIDATES[key]:
        if Path(candidate).exists():
            return candidate
    return None


@lru_cache(maxsize=1)
def resolve_ocr_font() -> str:
    """Register and return a Unicode-capable reportlab font name for invisible OCR text.

    Cached via ``lru_cache`` so font registration happens at most once per process.
    """
    from reportlab.pdfbase import pdfmetrics  # noqa: PLC0415

    try:
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont  # noqa: PLC0415
        name = "HeiseiKakuGo-W5"
        pdfmetrics.registerFont(UnicodeCIDFont(name))
        return name
    except Exception:  # noqa: BLE001
        pass

    font_path = _find_system_unicode_font()
    if font_path:
        try:
            from reportlab.pdfbase.ttfonts import TTFont  # noqa: PLC0415
            name = "_OcrUnicodeFont"
            pdfmetrics.registerFont(TTFont(name, font_path))
            return name
        except Exception:  # noqa: BLE001
            pass

    return "Helvetica"
