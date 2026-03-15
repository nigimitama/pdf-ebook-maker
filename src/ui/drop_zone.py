"""DropZone — drag-and-drop area with file/folder picker buttons.

Responsibility: accept file/folder drops and expose picker buttons.
Knows nothing about how the returned paths are stored or used.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .constants import BG_GRAY, BORDER, BORDER_LIGHT, CORAL, TEXT_MUTED, TEXT_SEC, WHITE


class DropZone(QWidget):
    """Accepts file/folder drops and surfaces picker buttons.

    Signals:
        files_dropped(list[str]): emitted with local paths of dropped items.

    Public attributes:
        btn_files (QPushButton): "choose files" button — connect externally.
        btn_folder (QPushButton): "choose folder" button — connect externally.
    """

    files_dropped = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(200)
        self._hovered = False
        self._setup_ui()
        self._apply_style()

    # ── UI construction ────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 24, 24, 24)

        layout.addWidget(self._make_icon())
        layout.addWidget(self._make_main_text())
        layout.addWidget(self._make_sub_text())
        layout.addWidget(self._make_or_divider())
        layout.addWidget(self._make_button_row())

    def _make_icon(self) -> QLabel:
        lbl = QLabel("⬆")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"font-size: 36px; color: {BORDER_LIGHT}; background: transparent;")
        return lbl

    def _make_main_text(self) -> QLabel:
        lbl = QLabel("ここにファイル・フォルダをドロップ")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {TEXT_SEC}; background: transparent;"
        )
        return lbl

    def _make_sub_text(self) -> QLabel:
        lbl = QLabel("PNG, JPG, WEBP 対応 / 複数選択可")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"font-size: 13px; color: {TEXT_MUTED}; background: transparent;")
        return lbl

    def _make_or_divider(self) -> QLabel:
        lbl = QLabel("— または —")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"font-size: 12px; color: {BORDER_LIGHT}; background: transparent;")
        return lbl

    def _make_button_row(self) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(row)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)

        self.btn_files = QPushButton("📄  ファイルを選択")
        self.btn_files.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_files.setStyleSheet(f"""
            QPushButton {{
                background: {CORAL}; color: white; border: none;
                border-radius: 8px; padding: 10px 20px;
                font-size: 14px; font-weight: 600;
            }}
            QPushButton:hover {{ background: #ff5252; }}
            QPushButton:pressed {{ background: #e53e3e; }}
        """)

        self.btn_folder = QPushButton("📁  フォルダを選択")
        self.btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_folder.setStyleSheet(f"""
            QPushButton {{
                background: {WHITE}; color: {TEXT_SEC};
                border: 1px solid {BORDER}; border-radius: 8px;
                padding: 10px 20px; font-size: 14px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {BG_GRAY}; }}
        """)

        layout.addWidget(self.btn_files)
        layout.addWidget(self.btn_folder)
        return row

    # ── Hover highlight ────────────────────────────────────────────────────────

    def _apply_style(self) -> None:
        if self._hovered:
            border_color, bg = CORAL, "#fff5f5"
        else:
            border_color, bg = BORDER_LIGHT, "#FAFAFA"
        self.setStyleSheet(f"""
            DropZone {{
                background: {bg};
                border: 2px dashed {border_color};
                border-radius: 16px;
            }}
        """)

    # ── Qt drag-and-drop overrides ─────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            self._hovered = True
            self._apply_style()
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self._hovered = False
        self._apply_style()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        self._hovered = False
        self._apply_style()
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        self.files_dropped.emit(paths)
        event.acceptProposedAction()
