"""StructurePanel — document structure editor shown between OCR and PDF generation.

Responsibility: display page categories and TOC entries; let the user edit them.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QDrag, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


from document_structure import (
    DocumentStructure,
    PageCategory,
    TocEntry,
)

from .constants import BG_GRAY, BORDER, BORDER_LIGHT, CORAL, INDIGO, TEXT_MUTED, TEXT_PRI, WHITE
from .toc_candidates_section import TocCandidatesSection

_TOC_BTN_ON = f"""
    QPushButton {{
        background: #3B82F6; color: {WHITE};
        border: none; border-radius: 8px;
        font-size: 10px; font-weight: 600; padding: 2px 8px;
    }}
    QPushButton:hover {{ background: #2563EB; }}
"""
_TOC_BTN_OFF = f"""
    QPushButton {{
        background: {BG_GRAY}; color: {TEXT_MUTED};
        border: 1px solid {BORDER_LIGHT}; border-radius: 8px;
        font-size: 10px; font-weight: 600; padding: 2px 8px;
    }}
    QPushButton:hover {{ background: {BORDER_LIGHT}; }}
"""

_SPINBOX_STYLE = f"""
    QSpinBox {{
        background: {BG_GRAY}; border: 1px solid {BORDER_LIGHT};
        border-radius: 6px; padding: 2px 6px;
        font-size: 12px; color: {TEXT_PRI};
    }}
"""

_SECTION_TITLE_STYLE = (
    f"font-size:13px; font-weight:600; color:{TEXT_PRI}; background:transparent; border:none;"
)


def _lbl(text: str, style: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(style)
    return lbl


# ── _DragHandle ────────────────────────────────────────────────────────────────

class _DragHandle(QLabel):
    """Drag handle label that initiates a QDrag to reorder TOC rows."""

    def __init__(self, row: QWidget) -> None:
        super().__init__("⠿")
        self._row = row
        self._start: QPoint | None = None
        self.setFixedWidth(16)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setToolTip("ドラッグして並び替え")
        self.setStyleSheet(
            f"color: {TEXT_MUTED}; background: transparent; font-size: 14px; padding: 0;"
        )

    def mousePressEvent(self, ev) -> None:  # type: ignore[override]
        if ev.button() == Qt.MouseButton.LeftButton:
            self._start = ev.pos()

    def mouseMoveEvent(self, ev) -> None:  # type: ignore[override]
        if (
            self._start is not None
            and ev.buttons() & Qt.MouseButton.LeftButton
            and (ev.pos() - self._start).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            self._start = None
            idx = self._current_index()
            if idx == -1:
                return
            mime = QMimeData()
            mime.setData("application/x-toc-row", str(idx).encode())
            drag = QDrag(self)
            drag.setMimeData(mime)
            drag.setPixmap(self._row.grab())
            drag.setHotSpot(QPoint(self._row.width() // 2, self._row.height() // 2))
            drag.exec(Qt.DropAction.MoveAction)

    def mouseReleaseEvent(self, ev) -> None:  # type: ignore[override]
        self._start = None

    def _current_index(self) -> int:
        container = self._row.parentWidget()
        if container is None:
            return -1
        layout = container.layout()
        if layout is None:
            return -1
        for i in range(layout.count() - 1):  # -1 to skip trailing stretch
            item = layout.itemAt(i)
            if item and item.widget() is self._row:
                return i
        return -1


# ── _TocListContainer ──────────────────────────────────────────────────────────

class _TocListContainer(QWidget):
    """Container for TOC rows; accepts drops and shows a drop-position indicator."""

    reorder_requested = Signal(int, int)  # (from_index, to_index)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self._drop_y: int | None = None

    def dragEnterEvent(self, ev) -> None:  # type: ignore[override]
        if ev.mimeData().hasFormat("application/x-toc-row"):
            ev.acceptProposedAction()

    def dragMoveEvent(self, ev) -> None:  # type: ignore[override]
        if ev.mimeData().hasFormat("application/x-toc-row"):
            self._drop_y = self._indicator_y(self._insert_index(ev.position().y()))
            self.update()
            ev.acceptProposedAction()

    def dragLeaveEvent(self, ev) -> None:  # type: ignore[override]
        self._drop_y = None
        self.update()

    def dropEvent(self, ev) -> None:  # type: ignore[override]
        self._drop_y = None
        self.update()
        from_idx = int(bytes(ev.mimeData().data("application/x-toc-row")).decode())
        to_idx = self._insert_index(ev.position().y())
        if to_idx != from_idx and to_idx != from_idx + 1:
            self.reorder_requested.emit(from_idx, to_idx)
        ev.acceptProposedAction()

    def paintEvent(self, ev) -> None:  # type: ignore[override]
        super().paintEvent(ev)
        if self._drop_y is None:
            return
        painter = QPainter(self)
        pen = QPen(QColor(INDIGO))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawLine(0, self._drop_y, self.width(), self._drop_y)

    def _insert_index(self, y: float) -> int:
        layout = self.layout()
        if layout is None:
            return 0
        count = layout.count() - 1  # exclude trailing stretch
        for i in range(count):
            item = layout.itemAt(i)
            if item:
                w = item.widget()
                if w and y < w.y() + w.height() / 2:
                    return i
        return count

    def _indicator_y(self, insert_before: int) -> int:
        layout = self.layout()
        if layout is None:
            return 0
        count = layout.count() - 1  # exclude trailing stretch
        if count == 0:
            return 0
        if insert_before == 0:
            item = layout.itemAt(0)
            if item:
                w = item.widget()
                if w:
                    return w.y()
            return 0
        if insert_before >= count:
            item = layout.itemAt(count - 1)
            if item:
                w = item.widget()
                if w:
                    return w.y() + w.height()
        else:
            item = layout.itemAt(insert_before)
            if item:
                w = item.widget()
                if w:
                    return w.y()
        return 0


class StructurePanel(QWidget):
    """Center panel: page-category list + TOC editor.

    Public methods:
        load(DocumentStructure): populate the panel with detected structure data.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._structure: DocumentStructure | None = None
        self._ocr_results: dict[str, list] = {}
        self._toc_rows: list[_TocRow] = []
        self._candidates_section = TocCandidatesSection()
        self.setStyleSheet(f"background: {WHITE};")
        self._setup_ui()

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def current_structure(self) -> DocumentStructure:
        """Return a DocumentStructure with current row values synced in."""
        if self._structure is not None:
            self._sync_toc_from_rows()
        return self._structure or DocumentStructure(pages=[], toc_entries=[])

    def load(
        self,
        structure: DocumentStructure,
        ocr_results: dict[str, list] | None = None,
    ) -> None:
        """Populate the panel with auto-detected document structure."""
        self._structure = structure
        self._ocr_results = ocr_results or {}
        # Start with no TOC entries — the user adds them manually via the candidates panel.
        self._structure.toc_entries = []
        self._populate_page_list()
        self._populate_toc_list()
        if ocr_results is not None:
            self._candidates_section.load(structure.pages, ocr_results)
    # ── UI construction ────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._make_body(), stretch=1)

    def _make_body(self) -> QWidget:
        body = QWidget()
        body.setStyleSheet(f"background: {WHITE};")
        layout = QHBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._make_page_column())
        layout.addWidget(self._make_toc_column(), stretch=1)
        return body

    # ── Page list column ───────────────────────────────────────────────────────

    def _make_page_column(self) -> QWidget:
        col = QWidget()
        col.setFixedWidth(320)
        col.setStyleSheet(f"background: {WHITE}; border-right: 1px solid {BORDER};")
        layout = QVBoxLayout(col)
        layout.setContentsMargins(16, 16, 12, 16)
        layout.setSpacing(8)

        hdr = QHBoxLayout()
        hdr.setSpacing(6)
        hdr.addWidget(_lbl("🖼", "font-size:13px; background:transparent; border:none;"))
        hdr.addWidget(_lbl("ページ一覧", _SECTION_TITLE_STYLE))
        hdr.addStretch()
        layout.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._page_list_container = QWidget()
        self._page_list_container.setStyleSheet("background: transparent;")
        self._page_list_layout = QVBoxLayout(self._page_list_container)
        self._page_list_layout.setContentsMargins(0, 0, 4, 0)
        self._page_list_layout.setSpacing(4)
        self._page_list_layout.addStretch()

        scroll.setWidget(self._page_list_container)
        layout.addWidget(scroll, stretch=1)
        return col

    def _populate_page_list(self) -> None:
        while self._page_list_layout.count() > 1:
            item = self._page_list_layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.deleteLater()

        if self._structure is None:
            return
        all_paths = [p.path for p in self._structure.pages]
        for page in self._structure.pages:
            ocr_lines = self._ocr_results.get(page.path, [])
            row = _PageRow(page.path, page.index, page.category, all_paths, ocr_lines)
            row.category_changed.connect(self._on_category_changed)
            row.remove_requested.connect(self._on_page_remove_requested)
            self._page_list_layout.insertWidget(
                self._page_list_layout.count() - 1, row
            )

    def _on_category_changed(self, index: int, cat: PageCategory) -> None:
        if self._structure is None:
            return
        self._structure.pages[index].category = cat
        self._candidates_section.load(self._structure.pages, self._ocr_results)

    def _on_page_remove_requested(self, page_index: int) -> None:
        """Remove page from structure and refresh the page list."""
        if self._structure is None:
            return
        self._structure.pages = [
            p for p in self._structure.pages if p.index != page_index
        ]
        self._populate_page_list()

    # ── TOC editor column ─────────────────────────────────────────────────────

    def _make_toc_column(self) -> QWidget:
        col = QWidget()
        col.setStyleSheet(f"background: {BG_GRAY};")
        layout = QVBoxLayout(col)
        layout.setContentsMargins(12, 16, 16, 16)
        layout.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setStyleSheet(f"QSplitter::handle {{ background: {BORDER}; height: 2px; }}")

        # Top: candidate lines from TOC pages (instance created in __init__)
        self._candidates_section.entry_added.connect(self._on_candidate_entry_added)
        splitter.addWidget(self._candidates_section)

        # Bottom: confirmed TOC entries
        splitter.addWidget(self._make_confirmed_entries_widget())
        splitter.setSizes([240, 260])

        layout.addWidget(splitter, stretch=1)
        return col

    def _make_confirmed_entries_widget(self) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet(f"background: {BG_GRAY};")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        hdr = QHBoxLayout()
        hdr.setSpacing(6)
        hdr.addWidget(_lbl("📋", "font-size:13px; background:transparent; border:none;"))
        hdr.addWidget(_lbl("目次エントリ", _SECTION_TITLE_STYLE))
        hdr.addStretch()

        add_btn = QPushButton("＋ 追加")
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: #F0F5FF; color: {INDIGO};
                border: none; border-radius: 8px;
                font-size: 11px; font-weight: 600; padding: 4px 10px;
            }}
            QPushButton:hover {{ background: #E0E7FF; }}
        """)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._add_toc_entry)
        hdr.addWidget(add_btn)
        layout.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._toc_list_container = _TocListContainer()
        self._toc_list_container.setStyleSheet("background: transparent;")
        self._toc_list_container.reorder_requested.connect(self._reorder_toc_rows)
        self._toc_list_layout = QVBoxLayout(self._toc_list_container)
        self._toc_list_layout.setContentsMargins(0, 0, 4, 0)
        self._toc_list_layout.setSpacing(6)
        self._toc_list_layout.addStretch()

        scroll.setWidget(self._toc_list_container)
        layout.addWidget(scroll, stretch=1)
        return widget

    def _on_candidate_entry_added(self, entry: TocEntry, candidate_line: object) -> None:
        if self._structure is None:
            return
        self._structure.toc_entries.append(entry)
        self._insert_toc_row(entry, candidate_line)

    def _populate_toc_list(self) -> None:
        for row in self._toc_rows:
            row.deleteLater()
        self._toc_rows.clear()

        if self._structure is None:
            return
        for entry in self._structure.toc_entries:
            self._insert_toc_row(entry)
        self._renumber_toc_rows()

    def _insert_toc_row(self, entry: TocEntry, candidate_line: object = None) -> None:
        page_count = len(self._structure.pages) if self._structure else 1
        image_paths = [p.path for p in self._structure.pages] if self._structure else []
        row = _TocRow(entry, page_count, image_paths, self._ocr_results, candidate_line)
        row.remove_requested.connect(self._remove_toc_row)
        row.level_changed.connect(self._renumber_toc_rows)
        self._toc_rows.append(row)
        self._toc_list_layout.insertWidget(
            self._toc_list_layout.count() - 1, row
        )
        self._renumber_toc_rows()

    def _add_toc_entry(self) -> None:
        if self._structure is None:
            return
        entry = TocEntry(title="", page_index=0, level=1)
        self._structure.toc_entries.append(entry)
        self._insert_toc_row(entry)

    def _remove_toc_row(self, row: _TocRow) -> None:
        if self._structure:
            self._structure.toc_entries = [
                e for e in self._structure.toc_entries if e is not row.entry
            ]
        if row in self._toc_rows:
            self._toc_rows.remove(row)
        row.unmark_candidate()
        row.deleteLater()
        self._renumber_toc_rows()

    def _renumber_toc_rows(self) -> None:
        """Update level badge numbers: sequential per level across all rows."""
        counters: dict[int, int] = {}
        for row in self._toc_rows:
            level = row.entry.level
            counters[level] = counters.get(level, 0) + 1
            row.set_index(counters[level])

    def _sync_toc_from_rows(self) -> None:
        """Write row widget values back into the TocEntry objects."""
        for row in self._toc_rows:
            row.sync_to_entry()

    def _reorder_toc_rows(self, from_idx: int, to_idx: int) -> None:
        n = len(self._toc_rows)
        if not (0 <= from_idx < n and 0 <= to_idx <= n):
            return
        actual_to = to_idx if to_idx <= from_idx else to_idx - 1
        row = self._toc_rows.pop(from_idx)
        self._toc_rows.insert(actual_to, row)
        self._toc_list_layout.removeWidget(row)
        self._toc_list_layout.insertWidget(actual_to, row)
        if self._structure:
            entry = self._structure.toc_entries.pop(from_idx)
            self._structure.toc_entries.insert(actual_to, entry)
        self._renumber_toc_rows()


# ── _PageRow ──────────────────────────────────────────────────────────────────

_THUMB_SIZE = 56


class _PageRow(QWidget):
    """One row in the page list: thumbnail (async), filename, category selector.

    Clicking the thumbnail opens a full-screen preview via PagePreviewDialog.
    """

    category_changed = Signal(int, str)   # (page_index, PageCategory)
    remove_requested = Signal(int)        # page_index

    def __init__(
        self,
        path: str,
        page_index: int,
        category: PageCategory,
        all_paths: list[str],
        ocr_lines: list | None = None,
    ) -> None:
        super().__init__()
        self._path = path
        self._page_index = page_index
        self._all_paths = all_paths
        self._ocr_lines = ocr_lines or []
        self._thumb_label: QLabel | None = None
        self._toc_btn: QPushButton | None = None
        self._build(path, category)
        self._start_thumbnail_load()

    def _build(self, path: str, category: PageCategory) -> None:
        border = CORAL if category == "cover" else BORDER
        self.setStyleSheet(f"""
            _PageRow {{
                background: {WHITE}; border: 1px solid {border};
                border-radius: 8px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        thumb = QLabel("🖼")
        thumb.setFixedSize(_THUMB_SIZE, _THUMB_SIZE)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setStyleSheet(
            f"background: {BG_GRAY}; border-radius: 8px; font-size: 18px;"
        )
        self._thumb_label = thumb
        layout.addWidget(thumb)

        info = QWidget()
        info.setStyleSheet("background: transparent;")
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(4)
        name_lbl = _lbl(Path(path).name, f"font-size:12px; font-weight:600; color:{TEXT_PRI};")
        name_lbl.setStyleSheet(name_lbl.styleSheet() + " background: transparent;")
        info_layout.addWidget(name_lbl)
        info_layout.addWidget(self._make_toc_toggle(category))
        layout.addWidget(info, stretch=1)

        del_btn = QPushButton("🗑")
        del_btn.setFixedSize(28, 28)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet("""
            QPushButton {
                background: #FEF2F2; border: none; border-radius: 6px;
                font-size: 12px; color: #EF4444;
            }
            QPushButton:hover { background: #FEE2E2; }
        """)
        del_btn.clicked.connect(lambda: self.remove_requested.emit(self._page_index))
        layout.addWidget(del_btn)

    def _start_thumbnail_load(self) -> None:
        from .thumbnail_worker import ThumbnailWorker  # noqa: PLC0415
        worker = ThumbnailWorker(self._path)
        worker.signals.ready.connect(self._on_thumbnail_ready)
        QThreadPool.globalInstance().start(worker)

    def _on_thumbnail_ready(self, px: QPixmap) -> None:
        if self._thumb_label is None:
            return
        scaled = px.scaled(
            _THUMB_SIZE, _THUMB_SIZE,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        if scaled.width() > _THUMB_SIZE or scaled.height() > _THUMB_SIZE:
            x = (scaled.width() - _THUMB_SIZE) // 2
            y = (scaled.height() - _THUMB_SIZE) // 2
            scaled = scaled.copy(x, y, _THUMB_SIZE, _THUMB_SIZE)
        self._thumb_label.setPixmap(scaled)
        self._thumb_label.setText("")
        self._thumb_label.setStyleSheet("background: transparent; border-radius: 8px;")
        self._thumb_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._thumb_label.mousePressEvent = (  # type: ignore[method-assign]
            lambda _: self._open_preview()
        )

    def _open_preview(self) -> None:
        from .page_preview_dialog import PagePreviewDialog  # noqa: PLC0415
        PagePreviewDialog(self._path, self._page_index, self._ocr_lines, self).exec()

    def _make_toc_toggle(self, category: PageCategory) -> QWidget:
        if category == "cover":
            badge = QLabel("表紙")
            badge.setStyleSheet(
                f"background: {CORAL}; color: {WHITE}; border-radius: 8px;"
                " font-size: 10px; font-weight: 600; padding: 2px 8px;"
            )
            return badge

        self._toc_btn = QPushButton("目次")
        self._toc_btn.setCheckable(True)
        self._toc_btn.setChecked(category == "toc")
        self._toc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toc_btn.setStyleSheet(_TOC_BTN_ON if category == "toc" else _TOC_BTN_OFF)
        self._toc_btn.clicked.connect(self._on_toc_toggle_clicked)
        return self._toc_btn

    def _on_toc_toggle_clicked(self) -> None:
        if self._toc_btn is None:
            return
        is_toc = self._toc_btn.isChecked()
        self._toc_btn.setStyleSheet(_TOC_BTN_ON if is_toc else _TOC_BTN_OFF)
        cat: PageCategory = "toc" if is_toc else "body"
        self.category_changed.emit(self._page_index, cat)


# ── _TocRow ───────────────────────────────────────────────────────────────────

class _TocRow(QWidget):
    """One TOC entry row: level badge, title input, page spinbox, delete button."""

    remove_requested = Signal(object)  # _TocRow
    level_changed = Signal()

    def __init__(
        self,
        entry: TocEntry,
        page_count: int,
        image_paths: list[str],
        ocr_results: dict[str, list],
        candidate_line: object = None,
    ) -> None:
        super().__init__()
        self.entry = entry
        self._page_count = page_count
        self._image_paths = image_paths
        self._ocr_results = ocr_results
        self._candidate_line = candidate_line
        self._build()

    def sync_to_entry(self) -> None:
        self.entry.title = self._title_edit.text()
        self.entry.page_index = self._page_spin.value() - 1
        self.entry.level = self._level_spin.value()

    def set_index(self, n: int) -> None:
        """Update the sequential number shown in the level badge."""
        self._level_lbl.setText(str(n))

    def unmark_candidate(self) -> None:
        """Revert the source candidate line's button to '目次に追加' if one exists."""
        if self._candidate_line is None:
            return
        try:
            self._candidate_line.mark_unadded()  # type: ignore[union-attr]
        except RuntimeError:
            pass  # Qt widget already deleted (e.g. after TOC page reload)

    def _build(self) -> None:
        self.setStyleSheet(f"""
            _TocRow {{
                background: {WHITE}; border: 1px solid {BORDER};
                border-radius: 10px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        layout.addWidget(_DragHandle(self))

        # Level badge (number updated externally via set_index)
        self._level_lbl = QLabel("·")
        self._level_lbl.setFixedSize(20, 20)
        self._level_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._level_lbl.setStyleSheet(f"""
            background: {INDIGO}; color: {WHITE};
            border-radius: 4px; font-size: 11px; font-weight: 700;
        """)
        layout.addWidget(self._level_lbl)

        # Title input
        self._title_edit = QLineEdit(self.entry.title)
        self._title_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {BG_GRAY}; border: 1px solid {BORDER_LIGHT};
                border-radius: 6px; padding: 4px 8px;
                font-size: 12px; color: {TEXT_PRI};
            }}
        """)
        layout.addWidget(self._title_edit, stretch=1)

        # Page spinbox (1-based display)
        self._page_spin = QSpinBox()
        self._page_spin.setRange(1, max(1, self._page_count))
        self._page_spin.setValue(self.entry.page_index + 1)
        self._page_spin.setFixedWidth(56)
        self._page_spin.setStyleSheet(_SPINBOX_STYLE)
        self._page_spin.setPrefix("p.")
        self._page_spin.valueChanged.connect(lambda v: self._load_thumb(v - 1))
        layout.addWidget(self._page_spin)

        # Page thumbnail
        self._thumb_lbl = QLabel()
        self._thumb_lbl.setFixedSize(32, 32)
        self._thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_lbl.setStyleSheet(
            f"background: {BG_GRAY}; border: 1px solid {BORDER_LIGHT}; border-radius: 4px;"
        )
        self._thumb_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._thumb_lbl.mousePressEvent = lambda _: self._on_thumb_clicked()
        layout.addWidget(self._thumb_lbl)
        self._load_thumb(self.entry.page_index)

        # Level spinbox
        self._level_spin = QSpinBox()
        self._level_spin.setRange(1, 3)
        self._level_spin.setValue(self.entry.level)
        self._level_spin.setFixedWidth(48)
        self._level_spin.setStyleSheet(_SPINBOX_STYLE)
        self._level_spin.setPrefix("L")
        self._level_spin.valueChanged.connect(self._on_level_changed)
        layout.addWidget(self._level_spin)

        # Delete button
        del_btn = QPushButton("✕")
        del_btn.setFixedSize(22, 22)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {BORDER_LIGHT};
                border: none; font-size: 13px; border-radius: 4px;
            }}
            QPushButton:hover {{ background: #fee2e2; color: #ef4444; }}
        """)
        del_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        layout.addWidget(del_btn)

    def _on_level_changed(self, v: int) -> None:
        self.entry.level = v
        self.level_changed.emit()

    def _load_thumb(self, page_index: int) -> None:
        if not self._image_paths or not (0 <= page_index < len(self._image_paths)):
            self._thumb_lbl.clear()
            return
        from .thumbnail_worker import ThumbnailWorker  # noqa: PLC0415
        worker = ThumbnailWorker(self._image_paths[page_index], size=32, radius=4)
        worker.signals.ready.connect(self._on_thumb_ready)
        QThreadPool.globalInstance().start(worker)

    def _on_thumb_ready(self, px: QPixmap) -> None:
        self._thumb_lbl.setPixmap(px)

    def _on_thumb_clicked(self) -> None:
        page_index = self._page_spin.value() - 1
        if not self._image_paths or not (0 <= page_index < len(self._image_paths)):
            return
        path = self._image_paths[page_index]
        ocr_lines = self._ocr_results.get(path, [])
        from .page_preview_dialog import PagePreviewDialog  # noqa: PLC0415
        PagePreviewDialog(path, page_index, ocr_lines, self).exec()
