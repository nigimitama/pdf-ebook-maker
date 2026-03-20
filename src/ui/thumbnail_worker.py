"""ThumbnailWorker — async thumbnail loader for use in thread-pool workers."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPixmap


class _ThumbnailSignals(QObject):
    ready = Signal(QPixmap)


class ThumbnailWorker(QRunnable):
    """Loads, crops, and round-corners a thumbnail in a thread-pool worker thread.

    On completion emits ``signals.ready(QPixmap)``.  Crop is center-square;
    corners are rounded with a 6 px radius.
    """

    def __init__(self, path: str, size: int = 36, radius: int = 6) -> None:
        super().__init__()
        self._path = path
        self._size = size
        self._radius = radius
        self.signals = _ThumbnailSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        px = self._load()
        if px is not None:
            self.signals.ready.emit(px)

    def _load(self) -> QPixmap | None:
        s, r = self._size, self._radius
        px = QPixmap(self._path)
        if px.isNull():
            return None
        px = px.scaled(s, s, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                       Qt.TransformationMode.SmoothTransformation)
        if px.width() > s or px.height() > s:
            x = (px.width() - s) // 2
            y = (px.height() - s) // 2
            px = px.copy(x, y, s, s)
        rounded = QPixmap(s, s)
        rounded.fill(Qt.GlobalColor.transparent)
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(0, 0, s, s, r, r)
        painter.setClipPath(clip)
        painter.drawPixmap(0, 0, px)
        painter.end()
        return rounded
