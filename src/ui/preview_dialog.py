"""ImagePreviewDialog — Before/After comparison of image processing results."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .constants import BG_GRAY, BORDER_LIGHT, TEXT_MUTED, TEXT_PRI, WHITE
from .preview_worker import PreviewSample

# Horizontal space consumed outside the two image columns
# dialog margins(16+16) + scroll margins(10+10) + row margins(12+12) + col margins(8+8)×2 + gap(12)
_H_OVERHEAD = 140
# Vertical space consumed outside the image itself inside one column
# top margin(6) + title label(20) + spacing(4) + bottom margin(8)
_COL_V_OVERHEAD = 38


def _to_pixmap(img: np.ndarray) -> QPixmap:
    img = np.ascontiguousarray(img)
    if img.ndim == 2:
        h, w = img.shape
        qimg = QImage(img.tobytes(), w, h, w, QImage.Format.Format_Grayscale8)
    else:
        rgb = np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        h, w, _ = rgb.shape
        qimg = QImage(rgb.tobytes(), w, h, w * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg)


def _screen_col_width() -> int:
    """Width each image column gets when the dialog is maximised."""
    screen_w = QApplication.primaryScreen().availableSize().width()
    return max(1, (screen_w - _H_OVERHEAD) // 2)


class _SampleRow(QWidget):
    def __init__(self, sample: PreviewSample, col_width: int) -> None:
        super().__init__()
        self._build(sample, col_width)

    def _build(self, sample: PreviewSample, col_width: int) -> None:
        self.setStyleSheet(
            f"background:{WHITE}; border:1px solid {BORDER_LIGHT}; border-radius:8px;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Header
        name_row = QHBoxLayout()
        name_row.setSpacing(12)
        name_lbl = QLabel(Path(sample.path).name)
        name_lbl.setStyleSheet(
            f"font-size:11px; font-weight:600; color:{TEXT_PRI}; background:transparent;"
        )
        size_lbl = QLabel(f"処理後 {sample.after_bytes / 1024:.0f} KB")
        size_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_MUTED}; background:transparent;"
        )
        name_row.addWidget(name_lbl, stretch=1)
        name_row.addWidget(size_lbl)
        layout.addLayout(name_row)

        # Before / After columns
        img_row = QHBoxLayout()
        img_row.setSpacing(12)
        for title, img in [("処理前", sample.before), ("処理後", sample.after)]:
            px = _to_pixmap(img)
            img_h = round(col_width * px.height() / max(px.width(), 1))
            scaled = px.scaled(
                col_width, img_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            col = QWidget()
            col.setStyleSheet(f"background:{BG_GRAY}; border-radius:6px;")
            col_layout = QVBoxLayout(col)
            col_layout.setContentsMargins(8, 6, 8, 8)
            col_layout.setSpacing(4)

            title_lbl = QLabel(title)
            title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_lbl.setStyleSheet(
                f"font-size:11px; font-weight:600; color:{TEXT_PRI}; background:transparent;"
            )
            col_layout.addWidget(title_lbl)

            img_lbl = QLabel()
            img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            img_lbl.setFixedSize(col_width, img_h + _COL_V_OVERHEAD)
            img_lbl.setPixmap(scaled)
            img_lbl.setStyleSheet("background:transparent;")
            col_layout.addWidget(img_lbl)

            img_row.addWidget(col)
        layout.addLayout(img_row)


class ImagePreviewDialog(QDialog):
    """Maximised dialog showing Before/After pairs and estimated PDF size."""

    def __init__(
        self,
        samples: list[PreviewSample],
        estimated_mb: float,
        total_count: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("仕上がり確認")
        self._build(samples, estimated_mb, total_count)
        self.showMaximized()

    def _build(
        self,
        samples: list[PreviewSample],
        estimated_mb: float,
        total_count: int,
    ) -> None:
        col_width = _screen_col_width()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        avg_kb = (
            sum(s.after_bytes for s in samples) / len(samples) / 1024
            if samples else 0
        )
        summary = QLabel(
            f"📄 推定PDFサイズ（画像のみ）: 約 {estimated_mb:.1f} MB"
            f"  （全 {total_count} 枚 × 平均 {avg_kb:.0f} KB/枚）"
            f"  ※ サンプル {len(samples)} 件から推定"
        )
        summary.setStyleSheet(
            f"font-size:13px; font-weight:600; color:{TEXT_PRI};"
            f" background:{BG_GRAY}; padding:10px 14px; border-radius:8px;"
        )
        layout.addWidget(summary)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea {{ border:1px solid {BORDER_LIGHT}; border-radius:8px;"
            f" background:{WHITE}; }}"
        )

        container = QWidget()
        container.setStyleSheet(f"background:{WHITE};")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(10, 10, 10, 10)
        container_layout.setSpacing(12)

        for sample in samples:
            container_layout.addWidget(_SampleRow(sample, col_width))
        container_layout.addStretch()

        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)
