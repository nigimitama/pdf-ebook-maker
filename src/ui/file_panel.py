"""FilePanel — left panel for file/folder drop and basic options.

Responsibility: collect the list of image paths via drag-and-drop or dialogs.
Emits ``files_changed`` whenever the selection changes.
File viewing and per-page management is handled by StructurePanel (Step 2).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .constants import BG_GRAY, BORDER, CORAL, TEXT_MUTED, TEXT_PRI, TEXT_SEC, WHITE
from .drop_zone import DropZone
from .progress_card import ProgressCard  # noqa: E402


def _lbl(text: str, style: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(style)
    return lbl


class FilePanel(QWidget):
    """Left panel: drag-and-drop zone for collecting image file paths.

    Signals:
        files_changed(list[str]): emitted whenever the selection changes.

    Properties:
        files (list[str]): read-only snapshot of the current selection.
    """

    files_changed = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._files: list[str] = []
        self.setFixedWidth(420)
        self.setStyleSheet(f"background: {WHITE}; border-right: 1px solid {BORDER};")
        self._setup_ui()

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def files(self) -> list[str]:
        """Read-only snapshot of the current selection."""
        return list(self._files)

    def set_progress(self, value: int, message: str, note: str = "") -> None:
        self._progress_card.set_progress(value, message, note)

    # ── UI construction ────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(0)

        layout.addWidget(self._make_section_header())
        layout.addSpacing(16)
        layout.addWidget(self._make_drop_zone())
        layout.addSpacing(16)
        layout.addWidget(self._make_clear_row())
        layout.addStretch()
        self._progress_card = ProgressCard()
        layout.addSpacing(16)
        layout.addWidget(self._progress_card)

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
        self._drop_zone = DropZone()
        self._drop_zone.files_dropped.connect(self._add_paths)
        self._drop_zone.btn_files.clicked.connect(self._browse_files)
        self._drop_zone.btn_folder.clicked.connect(self._browse_folder)
        return self._drop_zone

    def _make_clear_row(self) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch()

        clear_btn = QPushButton("🗑  クリア")
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

    # ── File management ────────────────────────────────────────────────────────

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
        self._files.extend(expanded)
        self._notify()

    def _clear(self) -> None:
        self._files.clear()
        self._notify()

    def _notify(self) -> None:
        has_files = len(self._files) > 0
        self._count_badge.setText(f"{len(self._files)} ファイル選択済み")
        self._drop_zone.setVisible(not has_files)
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
