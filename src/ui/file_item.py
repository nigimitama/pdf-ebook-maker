"""FileItem — a single row representing one file or folder in the selection list.

Responsibility: display name, metadata, and a remove button for one path entry.
Knows nothing about the list it lives in.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .constants import AMBER, BORDER, BORDER_LIGHT, INDIGO, TEXT_MUTED, TEXT_PRI, WHITE

_THUMB_SIZE = 36


def _rounded_pixmap(path: str, size: int = _THUMB_SIZE, radius: int = 6) -> QPixmap | None:
    """Load an image as a square pixmap with rounded corners. Returns None on failure."""
    px = QPixmap(path)
    if px.isNull():
        return None
    # Center-crop to square then scale
    px = px.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                   Qt.TransformationMode.SmoothTransformation)
    if px.width() > size or px.height() > size:
        x = (px.width() - size) // 2
        y = (px.height() - size) // 2
        px = px.copy(x, y, size, size)
    # Apply rounded-corner mask
    rounded = QPixmap(size, size)
    rounded.fill(Qt.GlobalColor.transparent)
    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(0, 0, size, size, radius, radius)
    painter.setClipPath(clip)
    painter.drawPixmap(0, 0, px)
    painter.end()
    return rounded


class FileItem(QWidget):
    """Displays one file/folder row: thumbnail, name, metadata, remove button.

    Signals:
        remove_requested(str): emitted with ``path`` when the remove button is clicked.
    """

    remove_requested = Signal(str)

    def __init__(self, path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = path
        p = Path(path)
        self.is_dir = p.is_dir()
        self._build(p)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build(self, p: Path) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        layout.addWidget(self._make_thumbnail())
        layout.addWidget(self._make_info(p), stretch=1)
        layout.addWidget(self._make_remove_button())

        self._apply_style()

    def _make_thumbnail(self) -> QLabel:
        thumb = QLabel()
        thumb.setFixedSize(_THUMB_SIZE, _THUMB_SIZE)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self.is_dir:
            thumb.setText("📁")
            thumb.setStyleSheet(
                f"background: #FFFBEB; border-radius: 6px; font-size: 18px; color: {AMBER};"
            )
        else:
            px = _rounded_pixmap(self.path)
            if px is not None:
                thumb.setPixmap(px)
                thumb.setStyleSheet("background: transparent;")
            else:
                thumb.setText("🖼")
                thumb.setStyleSheet(
                    f"background: #E0E7FF; border-radius: 6px; font-size: 18px; color: {INDIGO};"
                )
        return thumb

    def _make_info(self, p: Path) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        name_label = QLabel(p.name + ("/" if self.is_dir else ""))
        name_label.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {TEXT_PRI};")

        layout.addWidget(name_label)
        layout.addWidget(self._make_meta_label(p))
        return widget

    def _make_meta_label(self, p: Path) -> QLabel:
        if self.is_dir:
            label = QLabel(self._dir_meta(p))
            label.setStyleSheet(f"font-size: 11px; color: {AMBER};")
        else:
            label = QLabel(self._file_size(p))
            label.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
        return label

    def _make_remove_button(self) -> QPushButton:
        btn = QPushButton("✕")
        btn.setFixedSize(24, 24)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {BORDER_LIGHT};
                border: none; font-size: 14px; border-radius: 4px;
            }}
            QPushButton:hover {{ background: #fee2e2; color: #ef4444; }}
        """)
        btn.clicked.connect(lambda: self.remove_requested.emit(self.path))
        return btn

    def _apply_style(self) -> None:
        border_color, bg = ("#FCD34D", "#FFFBEB") if self.is_dir else (BORDER, WHITE)
        self.setStyleSheet(f"""
            FileItem {{
                background: {bg};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
        """)

    # ── Metadata helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _dir_meta(p: Path) -> str:
        try:
            count = sum(1 for f in p.iterdir() if f.is_file())
            return f"フォルダ  •  {count} ファイル"
        except OSError:
            return "フォルダ"

    @staticmethod
    def _file_size(p: Path) -> str:
        try:
            size = p.stat().st_size
            if size < 1024 * 1024:
                return f"{size / 1024:.0f} KB"
            return f"{size / 1024 / 1024:.1f} MB"
        except OSError:
            return ""
