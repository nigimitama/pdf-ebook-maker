"""ImagePreviewDialog — Before/After comparison of image processing results."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
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

_SPINBOX_STYLE = f"""
    QDoubleSpinBox {{
        background:{BG_GRAY}; border:1px solid {BORDER_LIGHT};
        border-radius:6px; padding:2px 6px;
        font-size:12px; color:{TEXT_PRI};
        min-width:90px;
    }}
"""


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
        self._col_width = col_width
        self._before_bgr = sample.before
        self._current_after_bgr: np.ndarray = sample.after
        self._path = sample.path
        self._after_lbl: QLabel | None = None
        self._fixed_img_h: int = 0
        self._angle_box: QDoubleSpinBox | None = None
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(400)
        self._render_timer.timeout.connect(self._update_after)
        self._build(sample, col_width)

    @property
    def path(self) -> str:
        return self._path

    def current_angle(self) -> float | None:
        return self._angle_box.value() if self._angle_box is not None else None

    def current_after_bgr(self) -> np.ndarray:
        return self._current_after_bgr

    def _build(self, sample: PreviewSample, col_width: int) -> None:
        self.setStyleSheet(
            f"background:{WHITE}; border:1px solid {BORDER_LIGHT}; border-radius:8px;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # ── Header ──────────────────────────────────────────────────────────
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_lbl = QLabel(Path(sample.path).name)
        name_lbl.setStyleSheet(
            f"font-size:11px; font-weight:600; color:{TEXT_PRI}; background:transparent;"
        )
        name_row.addWidget(name_lbl, stretch=1)

        if sample.angle is not None:
            angle_lbl = QLabel("補正角度:")
            angle_lbl.setStyleSheet(
                f"font-size:11px; color:{TEXT_MUTED}; background:transparent;"
            )
            spin = QDoubleSpinBox()
            spin.setRange(-45.0, 45.0)
            spin.setDecimals(2)
            spin.setSingleStep(0.1)
            spin.setValue(sample.angle)
            spin.setSuffix("°")
            spin.setStyleSheet(_SPINBOX_STYLE)
            spin.valueChanged.connect(self._on_angle_changed)
            self._angle_box = spin
            name_row.addWidget(angle_lbl)
            name_row.addWidget(spin)
        else:
            meta_lbl = QLabel(f"処理後 {sample.after_bytes / 1024:.0f} KB")
            meta_lbl.setStyleSheet(
                f"font-size:10px; color:{TEXT_MUTED}; background:transparent;"
            )
            name_row.addWidget(meta_lbl)

        layout.addLayout(name_row)

        # ── Image columns ────────────────────────────────────────────────────
        # Fix the display height to the before-image aspect ratio so the layout
        # does not shift when the user edits the angle (rotated images expand slightly).
        before_px = _to_pixmap(sample.before)
        img_h = round(col_width * before_px.height() / max(before_px.width(), 1))
        self._fixed_img_h = img_h

        img_row = QHBoxLayout()
        img_row.setSpacing(12)
        for title, img in [("処理前", sample.before), ("処理後", sample.after)]:
            px = _to_pixmap(img)
            scaled = px.scaled(
                col_width,
                img_h,
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

            if title == "処理後":
                self._after_lbl = img_lbl

            img_row.addWidget(col)

        layout.addLayout(img_row)

    def _on_angle_changed(self) -> None:
        self._render_timer.start()

    def _update_after(self) -> None:
        if self._angle_box is None or self._after_lbl is None:
            return
        from image_processing.rotation import rotate_image  # noqa: PLC0415

        angle = self._angle_box.value()
        before_rgb = cv2.cvtColor(self._before_bgr, cv2.COLOR_BGR2RGB)
        if abs(angle) < 0.05:
            after_bgr = self._before_bgr
        else:
            after_rgb = rotate_image(before_rgb, angle)
            after_bgr = cv2.cvtColor(after_rgb, cv2.COLOR_RGB2BGR)

        self._current_after_bgr = after_bgr
        px = _to_pixmap(after_bgr)
        scaled = px.scaled(
            self._col_width,
            self._fixed_img_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._after_lbl.setPixmap(scaled)


class ImagePreviewDialog(QDialog):
    """Maximised dialog showing Before/After pairs and estimated PDF size."""

    def __init__(
        self,
        samples: list[PreviewSample],
        estimated_mb: float,
        total_count: int,
        parent: QWidget | None = None,
        show_size_info: bool = True,
        header_text: str = "",
        accept_label: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("仕上がり確認")
        self._rows: list[_SampleRow] = []
        self._build(
            samples,
            estimated_mb,
            total_count,
            show_size_info,
            header_text,
            accept_label,
        )
        self.showMaximized()

    def get_angle_overrides(self) -> dict[str, float]:
        """Return {path: angle} for all rows that have an angle input."""
        result: dict[str, float] = {}
        for row in self._rows:
            angle = row.current_angle()
            if angle is not None:
                result[row.path] = angle
        return result

    def update_samples_in_place(self, original_samples: list[PreviewSample]) -> None:
        """Update samples with angle and after-image confirmed by the user (mutates in place)."""
        row_map = {row.path: row for row in self._rows}
        for sample in original_samples:
            row = row_map.get(sample.path)
            if row is None:
                continue
            if row.current_angle() is not None:
                sample.angle = row.current_angle()
            sample.after = row.current_after_bgr()

    def _build(
        self,
        samples: list[PreviewSample],
        estimated_mb: float,
        total_count: int,
        show_size_info: bool,
        header_text: str,
        accept_label: str,
    ) -> None:
        col_width = _screen_col_width()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        if show_size_info:
            avg_kb = (
                sum(s.after_bytes for s in samples) / len(samples) / 1024
                if samples
                else 0
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
        elif header_text:
            header = QLabel(header_text)
            header.setStyleSheet(
                f"font-size:13px; font-weight:600; color:{TEXT_PRI};"
                f" background:{BG_GRAY}; padding:10px 14px; border-radius:8px;"
            )
            layout.addWidget(header)

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
            row = _SampleRow(sample, col_width)
            self._rows.append(row)
            container_layout.addWidget(row)
        container_layout.addStretch()

        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

        if accept_label:
            btn_box = QDialogButtonBox()
            accept_btn = btn_box.addButton(
                accept_label, QDialogButtonBox.ButtonRole.AcceptRole
            )
            reject_btn = btn_box.addButton(
                "キャンセル", QDialogButtonBox.ButtonRole.RejectRole
            )
            accept_btn.setStyleSheet(
                "QPushButton { background:#FF6B6B; color:white; border:none;"
                " border-radius:8px; padding:8px 20px; font-size:13px; font-weight:600; }"
                "QPushButton:hover { background:#e05555; }"
                "QPushButton:pressed { background:#c94444; }"
            )
            reject_btn.setStyleSheet(
                f"QPushButton {{ background:{BG_GRAY}; color:{TEXT_PRI}; border:1px solid {BORDER_LIGHT};"
                " border-radius:8px; padding:8px 20px; font-size:13px; }"
                f"QPushButton:hover {{ background:#e8e9eb; }}"
            )
            btn_box.accepted.connect(self.accept)
            btn_box.rejected.connect(self.reject)
            layout.addWidget(btn_box)
