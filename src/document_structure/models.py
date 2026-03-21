"""Document structure data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

PageCategory = Literal["cover", "toc", "body", "uncategorized"]

_CATEGORY_LABELS: dict[PageCategory, str] = {
    "cover": "表紙",
    "toc": "目次",
    "body": "本文",
    "uncategorized": "未分類",
}


def category_label(cat: PageCategory) -> str:
    return _CATEGORY_LABELS[cat]


@dataclass
class PageEntry:
    """One image page with its assigned category."""

    path: str
    index: int          # 0-based position in the document
    category: PageCategory


@dataclass
class TocEntry:
    """One table-of-contents entry pointing to a page."""

    title: str
    page_index: int     # 0-based index into DocumentStructure.pages
    level: int = 1      # heading level: 1=chapter, 2=section, 3=subsection


@dataclass
class DocumentStructure:
    """Complete structural description of the document."""

    pages: list[PageEntry]
    toc_entries: list[TocEntry] = field(default_factory=list)
    suggested_title: str = ""
