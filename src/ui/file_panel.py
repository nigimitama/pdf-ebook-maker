"""FilePanel — left panel that owns the file/folder selection list.

Responsibility: manage the list of selected paths; surface file/folder dialogs.
Emits ``files_changed`` whenever the list changes so the parent can react
(e.g. enable/disable the Run button) without knowing about file-list internals.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .constants import BG_GRAY, BORDER, CORAL, TEXT_MUTED, TEXT_PRI, TEXT_SEC, WHITE
from .drop_zone import DropZone
from .file_item import FileItem, _PreviewDialog


def _lbl(text: str, style: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(style)
    return lbl


class FilePanel(QWidget):
    """Left panel: drag-and-drop zone + scrollable selected-files list.

    Signals:
        files_changed(list[str]): emitted whenever the selection changes.

    Properties:
        files (list[str]): read-only snapshot of the current selection.
    """

    files_changed = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._files: list[str] = []
        self.setFixedWidth(660)
        self.setStyleSheet(f"background: {WHITE}; border-right: 1px solid {BORDER};")
        self._setup_ui()

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def files(self) -> list[str]:
        """Read-only snapshot of the current selection."""
        return list(self._files)

    # ── UI construction ────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(0)

        layout.addWidget(self._make_section_header())
        layout.addSpacing(16)
        layout.addWidget(self._make_drop_zone())
        layout.addSpacing(16)
        layout.addWidget(self._make_list_header())
        layout.addSpacing(8)
        layout.addWidget(self._make_file_list_scroll(), stretch=1)

    def _make_section_header(self) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet(f"border-bottom: 1px solid {BORDER}; background: transparent;")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 16)
        layout.setSpacing(8)

        layout.addWidget(_lbl("🖼", f"font-size:16px; color:{CORAL}; background:transparent; border:none;"))
        layout.addWidget(_lbl("画像ファイル", f"font-size:16px; font-weight:700; color:{TEXT_PRI}; background:transparent; border:none;"))

        self._count_badge = QLabel("0 ファイル選択済み")
        self._count_badge.setStyleSheet(f"""
            background: {BG_GRAY}; color: {TEXT_SEC};
            padding: 4px 10px; border-radius: 12px;
            font-size: 12px; font-weight: 500; border: none;
        """)
        layout.addWidget(self._count_badge)
        layout.addStretch()
        return widget

    def _make_drop_zone(self) -> DropZone:
        zone = DropZone()
        zone.files_dropped.connect(self._add_paths)
        zone.btn_files.clicked.connect(self._browse_files)
        zone.btn_folder.clicked.connect(self._browse_folder)
        return zone

    def _make_list_header(self) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(_lbl("選択済みファイル", f"font-size:14px; font-weight:600; color:{TEXT_PRI};"))
        layout.addStretch()

        clear_btn = QPushButton("🗑  クリア")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_GRAY}; color: {TEXT_MUTED};
                border: none; border-radius: 6px;
                padding: 4px 10px; font-size: 12px;
            }}
            QPushButton:hover {{ background: #fee2e2; color: #ef4444; }}
        """)
        clear_btn.clicked.connect(self._clear)
        layout.addWidget(clear_btn)
        return widget

    def _make_file_list_scroll(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._list_container = QWidget()
        self._list_container.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 4, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()

        scroll.setWidget(self._list_container)
        return scroll

    # ── File list management ───────────────────────────────────────────────────

    _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}

    def _expand(self, paths: list[str]) -> list[str]:
        """Expand folder paths to their image-file contents; pass file paths through."""
        result: list[str] = []
        for p in paths:
            path = Path(p)
            if path.is_dir():
                result.extend(
                    str(f) for f in sorted(path.iterdir())
                    if f.is_file() and f.suffix.lower() in self._IMAGE_EXTS
                )
            else:
                result.append(p)
        return result

    def _add_paths(self, paths: list[str]) -> None:
        expanded = [p for p in self._expand(paths) if p not in self._files]
        if not expanded:
            return
        self._count_badge.setText("追加中...")
        for p in expanded:
            self._files.append(p)
            self._insert_item(p)
        self._notify()

    def _insert_item(self, path: str) -> None:
        item = FileItem(path)
        item.remove_requested.connect(self._remove_path)
        item.preview_requested.connect(self._open_preview)
        # Insert before the trailing stretch item
        self._list_layout.insertWidget(self._list_layout.count() - 1, item)

    def _open_preview(self, path: str) -> None:
        try:
            index = self._files.index(path)
        except ValueError:
            index = 0
        _PreviewDialog(self._files, index, self).exec()

    def _remove_path(self, path: str) -> None:
        if path in self._files:
            self._files.remove(path)
        for i in range(self._list_layout.count()):
            layout_item = self._list_layout.itemAt(i)
            if layout_item is None:
                continue
            w = layout_item.widget()
            if isinstance(w, FileItem) and w.path == path:
                w.deleteLater()
                break
        self._notify()

    def _clear(self) -> None:
        self._files.clear()
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.deleteLater()
        self._notify()

    def _notify(self) -> None:
        self._count_badge.setText(f"{len(self._files)} ファイル選択済み")
        self.files_changed.emit(list(self._files))

    # ── File dialogs ───────────────────────────────────────────────────────────

    def _browse_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "画像ファイルを選択",
            "",
            "画像ファイル (*.png *.jpg *.jpeg *.webp *.bmp *.tiff *.tif)",
        )
        if paths:
            self._add_paths(paths)

    def _browse_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "フォルダを選択")
        if path:
            self._add_paths([path])
