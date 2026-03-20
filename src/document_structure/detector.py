"""Auto-detect page categories and TOC entries from OCR results."""

from __future__ import annotations

import re

from .models import DocumentStructure, PageCategory, PageEntry, TocEntry

# Keywords that identify a TOC page
_TOC_KEYWORDS = re.compile(
    r"(目次|もくじ|CONTENTS|contents|目　次)",
    re.IGNORECASE,
)

# Patterns for TOC entry lines:  「第X章　タイトル ・・・ 3」
_CHAPTER_PATTERN = re.compile(
    r"第\s*(\d+|[一二三四五六七八九十]+)\s*章\s*(.+?)[\s・…_．.]{2,}\s*(\d+)\s*$"
)
_SECTION_PATTERN = re.compile(
    r"第\s*(\d+|[一二三四五六七八九十]+)\s*節\s*(.+?)[\s・…_．.]{2,}\s*(\d+)\s*$"
)
_GENERIC_PATTERN = re.compile(
    r"^(.+?)[\s・…_．.]{3,}\s*(\d+)\s*$"
)

# Characters illegal in file names (Windows + POSIX overlap)
_ILLEGAL_FILENAME_CHARS = re.compile(r'[/\\:*?"<>|]')


def build_structure(
    image_paths: list[str],
    ocr_results: dict[str, list],
) -> DocumentStructure:
    """Build a DocumentStructure from ordered image paths and OCR results.

    Parameters
    ----------
    image_paths:  Ordered list of image file paths (already sorted as desired).
    ocr_results:  Mapping of image path → list[OcrResult].
    """
    pages = _assign_categories(image_paths, ocr_results)
    toc_entries = _extract_toc_entries(pages, ocr_results)
    suggested_title = _suggest_title(pages, ocr_results)
    return DocumentStructure(
        pages=pages,
        toc_entries=toc_entries,
        suggested_title=suggested_title,
    )


def _assign_categories(
    image_paths: list[str],
    ocr_results: dict[str, list],
) -> list[PageEntry]:
    pages: list[PageEntry] = []
    for i, path in enumerate(image_paths):
        if i == 0:
            category: PageCategory = "cover"
        else:
            text = _join_text(ocr_results.get(path, []))
            if _TOC_KEYWORDS.search(text):
                category = "toc"
            else:
                category = "body"
        pages.append(PageEntry(path=path, index=i, category=category))
    return pages


def _extract_toc_entries(
    pages: list[PageEntry],
    ocr_results: dict[str, list],
) -> list[TocEntry]:
    """Parse TOC entries from pages categorised as 'toc'."""
    entries: list[TocEntry] = []
    toc_pages = [p for p in pages if p.category == "toc"]
    page_count = len(pages)

    for page in toc_pages:
        text = _join_text(ocr_results.get(page.path, []))
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            entry = parse_toc_line(line, page_count)
            if entry is not None:
                entries.append(entry)

    return entries


def parse_toc_line(line: str, page_count: int) -> TocEntry | None:
    """Parse one line of text into a TocEntry, or None if it doesn't look like a TOC entry."""
    m = _CHAPTER_PATTERN.search(line)
    if m:
        title = f"第{m.group(1)}章 {m.group(2).strip()}"
        page_num = _clamp(int(m.group(3)) - 1, page_count)
        return TocEntry(title=title, page_index=page_num, level=1)

    m = _SECTION_PATTERN.search(line)
    if m:
        title = f"第{m.group(1)}節 {m.group(2).strip()}"
        page_num = _clamp(int(m.group(3)) - 1, page_count)
        return TocEntry(title=title, page_index=page_num, level=2)

    m = _GENERIC_PATTERN.match(line)
    if m:
        title = m.group(1).strip()
        if len(title) < 2:  # skip stray single characters
            return None
        page_num = _clamp(int(m.group(2)) - 1, page_count)
        return TocEntry(title=title, page_index=page_num, level=1)

    return None


def _suggest_title(
    pages: list[PageEntry],
    ocr_results: dict[str, list],
) -> str:
    """Extract a filename-safe title suggestion from the cover page's OCR."""
    if not pages:
        return ""
    cover = pages[0]
    text = _join_text(ocr_results.get(cover.path, []))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    # Pick the longest non-trivial line as the title candidate
    candidate = max(lines, key=len)
    return _ILLEGAL_FILENAME_CHARS.sub("", candidate)[:80]


def _join_text(results: list) -> str:
    return "\n".join(r.text for r in results if r.text)


def _clamp(value: int, page_count: int) -> int:
    return max(0, min(value, page_count - 1))
