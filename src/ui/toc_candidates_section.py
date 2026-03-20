"""TocCandidatesSection — interactive panel for selecting TOC entries from OCR text.

Shows OCR lines from pages categorised as 'toc'. Each line has an "目次に追加" button.
A page-offset spinbox lets the user declare which image number is "page 1" so that
trailing page numbers in TOC lines are mapped to the correct image index.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from document_structure import PageEntry, TocEntry, parse_toc_line

from .constants import BG_GRAY, BORDER_LIGHT, INDIGO, TEXT_MUTED, TEXT_PRI, WHITE

_TRAILING_NUM_RE = re.compile(r"(\d{1,3})\s*$")


def _lbl(text: str, style: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(style)
    return lbl


def _extract_trailing_page_number(line: str) -> int | None:
    m = _TRAILING_NUM_RE.search(line)
    return int(m.group(1)) if m else None


_BTN_ADD_STYLE = f"""
    QPushButton {{
        background: #EEF2FF; color: {INDIGO};
        border: 1px solid #C7D2FE; border-radius: 6px;
        font-size: 10px; font-weight: 600;
        padding: 2px 7px; min-width: 64px;
    }}
    QPushButton:hover {{ background: #E0E7FF; }}
    QPushButton:pressed {{ background: #C7D2FE; }}
"""

_BTN_ADDED_STYLE = f"""
    QPushButton {{
        background: {BG_GRAY}; color: {TEXT_MUTED};
        border: 1px solid {BORDER_LIGHT}; border-radius: 6px;
        font-size: 10px; font-weight: 600;
        padding: 2px 7px; min-width: 64px;
    }}
"""


class _TocCandidateLine(QWidget):
    """A single OCR text line with an '目次に追加' button."""

    # Emits (parsed: TocEntry | None, raw_line: str) — parent applies page offset
    add_requested = Signal(object, str)

    def __init__(self, line: str, parsed: TocEntry | None) -> None:
        super().__init__()
        self._line = line
        self._parsed = parsed
        self._build()

    def mark_added(self) -> None:
        """Show the line as already added (pre-populated or just clicked)."""
        self._add_btn.setText("追加済み")
        self._add_btn.setStyleSheet(_BTN_ADDED_STYLE)
        self._add_btn.setEnabled(False)

    def _build(self) -> None:
        self.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 1, 2, 1)
        layout.setSpacing(6)

        if self._parsed:
            display = self._parsed.title
            hint = f"p.{self._parsed.page_index + 1}  L{self._parsed.level}"
            hint_color = INDIGO
        else:
            display = self._line
            hint = ""
            hint_color = TEXT_MUTED

        layout.addWidget(
            _lbl(display, f"font-size:12px; color:{TEXT_PRI}; background:transparent;"),
            stretch=1,
        )
        layout.addWidget(
            _lbl(hint, f"font-size:10px; color:{hint_color}; background:transparent;")
        )

        self._add_btn = QPushButton("目次に追加")
        self._add_btn.setStyleSheet(_BTN_ADD_STYLE)
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.clicked.connect(self._on_add_clicked)
        layout.addWidget(self._add_btn)

    def _on_add_clicked(self) -> None:
        self.mark_added()
        self.add_requested.emit(self._parsed, self._line)


class TocCandidatesSection(QWidget):
    """Panel listing OCR text lines from 'toc' pages for interactive entry addition.

    Each line has an '目次に追加' button. A page-offset spinbox converts the book's
    page numbers (as printed) to image indices in the PDF.

    Emits entry_added as the user clicks buttons.
    Pre-marks lines that matched existing auto-detected entries as '追加済み'.
    """

    entry_added = Signal(object)  # TocEntry

    def __init__(self) -> None:
        super().__init__()
        self._candidate_lines: list[_TocCandidateLine] = []
        self._build()

    @property
    def page_offset(self) -> int:
        """0-based index of the image that corresponds to book page 1."""
        return self._page_offset_spin.value() - 1

    def load(
        self,
        pages: list[PageEntry],
        ocr_results: dict[str, list],
        existing_entries: list[TocEntry],
    ) -> None:
        """Populate from the given TOC pages and pre-mark auto-detected entries."""
        self._clear()
        page_count = len(pages)
        toc_pages = [(p, ocr_results.get(p.path, [])) for p in pages if p.category == "toc"]
        if not toc_pages:
            self._show_empty_message()
            return

        for page, results in toc_pages:
            self._list_layout.insertWidget(
                self._list_layout.count() - 1,
                self._make_page_separator(page),
            )
            for result in results:
                line = result.text.strip()
                if not line:
                    continue
                parsed = parse_toc_line(line, page_count)
                cl = _TocCandidateLine(line, parsed)
                cl.add_requested.connect(self._on_add_requested)
                if parsed:
                    already_added = any(
                        e.title == parsed.title and e.page_index == parsed.page_index
                        for e in existing_entries
                    )
                    if already_added:
                        cl.mark_added()
                self._list_layout.insertWidget(self._list_layout.count() - 1, cl)
                self._candidate_lines.append(cl)

    # ── private ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.setStyleSheet(f"background: {BG_GRAY};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        layout.addWidget(self._make_header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {BORDER_LIGHT};"
            f" border-radius: 8px; background: {WHITE}; }}"
        )
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._container.setStyleSheet(f"background: {WHITE};")
        self._list_layout = QVBoxLayout(self._container)
        self._list_layout.setContentsMargins(8, 8, 4, 8)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch()

        scroll.setWidget(self._container)
        layout.addWidget(scroll, stretch=1)

    def _make_header(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(
            _lbl(
                "📑 目次候補ページのテキスト",
                f"font-size:12px; font-weight:600; color:{TEXT_PRI}; background:transparent;",
            )
        )
        layout.addStretch()

        layout.addWidget(
            _lbl(
                "ページ1 =",
                f"font-size:11px; color:{TEXT_MUTED}; background:transparent;",
            )
        )
        self._page_offset_spin = QSpinBox()
        self._page_offset_spin.setRange(1, 999)
        self._page_offset_spin.setValue(1)
        self._page_offset_spin.setFixedWidth(54)
        self._page_offset_spin.setStyleSheet(f"""
            QSpinBox {{
                background: {WHITE}; border: 1px solid {BORDER_LIGHT};
                border-radius: 5px; padding: 1px 4px;
                font-size: 11px; color: {TEXT_PRI};
            }}
        """)
        self._page_offset_spin.setToolTip(
            "PDFの何枚目の画像を「ページ1」とするか（表紙などを除いた最初の本文ページの画像番号）"
        )
        layout.addWidget(self._page_offset_spin)
        layout.addWidget(
            _lbl(
                "枚目",
                f"font-size:11px; color:{TEXT_MUTED}; background:transparent;",
            )
        )
        return w

    def _on_add_requested(self, parsed: TocEntry | None, raw_line: str) -> None:
        offset = self.page_offset  # 0-based index of image that is page 1
        if parsed:
            # parsed.page_index = book_page_num - 1 (0-based, no cover offset)
            # adjusted: shift by offset so image 'offset' becomes page 1
            page_index = parsed.page_index + offset
            entry = TocEntry(parsed.title, page_index, parsed.level)
        else:
            raw_num = _extract_trailing_page_number(raw_line)
            page_index = (raw_num - 1 + offset) if raw_num is not None else offset
            entry = TocEntry(raw_line[:80], page_index, 1)
        self.entry_added.emit(entry)

    def _clear(self) -> None:
        for cl in self._candidate_lines:
            cl.add_requested.disconnect()
        self._candidate_lines.clear()
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _show_empty_message(self) -> None:
        lbl = _lbl(
            "目次ページが検出されませんでした\n"
            "ページ一覧でカテゴリを「目次」に変更してください",
            f"font-size:12px; color:{TEXT_MUTED}; background:transparent;",
        )
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list_layout.insertWidget(self._list_layout.count() - 1, lbl)

    def _make_page_separator(self, page: PageEntry) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {BG_GRAY}; border-radius: 4px;")
        layout = QHBoxLayout(w)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.addWidget(
            _lbl(
                f"── p.{page.index + 1}  {Path(page.path).name}",
                f"font-size:10px; color:{TEXT_MUTED}; font-weight:600; background:transparent;",
            )
        )
        return w
