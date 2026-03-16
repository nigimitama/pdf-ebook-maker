"""FileItem — a single row representing one image file in the selection list.

Responsibility: display thumbnail, name, file size, and a remove button.
Knows nothing about the list it lives in.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .constants import BORDER, BORDER_LIGHT, INDIGO, TEXT_MUTED, TEXT_PRI, WHITE

_THUMB_SIZE = 36


def _rounded_pixmap(path: str, size: int = _THUMB_SIZE, radius: int = 6) -> QPixmap | None:
    """Load an image as a square pixmap with rounded corners. Returns None on failure."""
    px = QPixmap(path)
    if px.isNull():
        return None
    px = px.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                   Qt.TransformationMode.SmoothTransformation)
    if px.width() > size or px.height() > size:
        x = (px.width() - size) // 2
        y = (px.height() - size) // 2
        px = px.copy(x, y, size, size)
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


class _PreviewDialog(QDialog):
    """Full-screen dark-overlay image preview with keyboard navigation.

    Left/Right arrows move between images. Click anywhere or Escape to close.
    """

    def __init__(self, paths: list[str], index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._paths = paths
        self._index = index

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        screen = QApplication.primaryScreen()
        geom = screen.availableGeometry() if screen else self.rect()
        self.setGeometry(geom)
        self._geom = geom
        self._max_w = geom.width() - 120
        self._max_h = geom.height() - 120

        self._img_label = QLabel(self)
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._name_label = QLabel(self)
        self._name_label.setStyleSheet(
            "color: white; background: rgba(0,0,0,140);"
            " padding: 6px 12px; border-radius: 6px;"
            " font-size: 13px; font-weight: 600;"
        )
        self._name_label.move(20, 20)

        self._load(index)

    def _load(self, index: int) -> None:
        self._index = index
        path = self._paths[index]
        px = QPixmap(path)
        if not px.isNull():
            px = px.scaled(self._max_w, self._max_h,
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        self._img_label.setPixmap(px)
        self._img_label.resize(px.width(), px.height())
        self._img_label.move(
            (self._geom.width() - px.width()) // 2,
            (self._geom.height() - px.height()) // 2,
        )
        self._name_label.setText(Path(path).name)
        self._name_label.adjustSize()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 190))

    def mousePressEvent(self, _event) -> None:  # type: ignore[override]
        self.close()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.close()
        elif key == Qt.Key.Key_Right and self._index < len(self._paths) - 1:
            self._load(self._index + 1)
        elif key == Qt.Key.Key_Left and self._index > 0:
            self._load(self._index - 1)
        else:
            super().keyPressEvent(event)


class FileItem(QWidget):
    """Displays one image-file row: thumbnail, name, file size, remove button.

    Signals:
        remove_requested(str): emitted with ``path`` when the remove button is clicked.
    """

    remove_requested = Signal(str)
    preview_requested = Signal(str)

    def __init__(self, path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = path
        self._build(Path(path))

    # ── UI construction ────────────────────────────────────────────────────────

    def _build(self, p: Path) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)
        layout.addWidget(self._make_thumbnail())
        layout.addWidget(self._make_info(p), stretch=1)
        layout.addWidget(self._make_remove_button())
        self.setStyleSheet(f"""
            FileItem {{
                background: {WHITE}; border: 1px solid {BORDER}; border-radius: 8px;
            }}
        """)

    def _make_thumbnail(self) -> QLabel:
        thumb = QLabel()
        thumb.setFixedSize(_THUMB_SIZE, _THUMB_SIZE)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        px = _rounded_pixmap(self.path)
        if px is not None:
            thumb.setPixmap(px)
            thumb.setStyleSheet("background: transparent;")
            thumb.setCursor(Qt.CursorShape.PointingHandCursor)
            thumb.mousePressEvent = lambda _: self.preview_requested.emit(self.path)  # type: ignore[method-assign]
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

        name_label = QLabel(p.name)
        name_label.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {TEXT_PRI};")
        size_label = QLabel(self._file_size(p))
        size_label.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")

        layout.addWidget(name_label)
        layout.addWidget(size_label)
        return widget

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

    # ── Metadata helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _file_size(p: Path) -> str:
        try:
            size = p.stat().st_size
            if size < 1024 * 1024:
                return f"{size / 1024:.0f} KB"
            return f"{size / 1024 / 1024:.1f} MB"
        except OSError:
            return ""
