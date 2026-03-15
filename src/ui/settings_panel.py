"""SettingsPanel — right panel with output settings, options, run button, and progress.

Responsibility: collect PDF generation configuration; surface run/progress state.
Does not know which files will be processed — the parent passes that context.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .constants import BG_GRAY, BORDER, BORDER_LIGHT, CORAL, TEXT_MUTED, TEXT_PRI, TEXT_SEC, WHITE
from .output_card import OutputCard
from .progress_card import ProgressCard
from .run_options import RunOptions

__all__ = ["RunOptions", "SettingsPanel"]

_CB_STYLE = f"""
    QCheckBox {{
        font-size: 13px; color: {TEXT_PRI};
        spacing: 10px; background: transparent; border: none;
    }}
    QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 4px; }}
    QCheckBox::indicator:checked {{ background: {CORAL}; border: none; image: url(none); }}
    QCheckBox::indicator:unchecked {{
        background: white; border: 2px solid {BORDER_LIGHT}; border-radius: 4px;
    }}
"""

_SPINBOX_STYLE = f"""
    QSpinBox, QDoubleSpinBox {{
        background: {BG_GRAY}; border: 1px solid {BORDER_LIGHT};
        border-radius: 6px; padding: 2px 6px;
        font-size: 13px; color: {TEXT_PRI};
    }}
    QSpinBox:disabled, QDoubleSpinBox:disabled {{
        color: {TEXT_MUTED}; border-color: {BORDER};
    }}
"""


def _lbl(text: str, style: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(style)
    return lbl


def _card() -> tuple[QWidget, QVBoxLayout]:
    """Return a white rounded card widget and its pre-configured layout."""
    card = QWidget()
    card.setStyleSheet(f"""
        QWidget {{ background: {WHITE}; border-radius: 16px; border: 1px solid {BORDER}; }}
    """)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(12)
    return card, layout


class SettingsPanel(QWidget):
    """Right panel: output path/name, options, run button, progress display.

    Signals:
        run_requested(RunOptions): emitted when the user clicks Run.

    Public methods:
        set_run_enabled(bool)        -- enable/disable the Run button.
        set_running(bool)            -- toggle busy state.
        set_progress(int, str, str)  -- update progress bar and status text.
    """

    run_requested = Signal(object)  # RunOptions

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background: {BG_GRAY};")
        self._setup_ui()

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_run_enabled(self, enabled: bool) -> None:
        self._run_btn.setEnabled(enabled)

    def set_running(self, running: bool) -> None:
        self._run_btn.setEnabled(not running)

    def set_progress(self, value: int, message: str, note: str = "") -> None:
        self._progress_card.set_progress(value, message, note)

    # ── UI construction ────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        self._output_card = OutputCard()
        layout.addWidget(self._output_card)
        layout.addWidget(self._make_options_card())
        layout.addStretch()
        layout.addWidget(self._make_run_section())

    def _make_options_card(self) -> QWidget:
        card, layout = _card()

        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        hdr.addWidget(_lbl("⚙", "font-size:16px; background:transparent; border:none;"))
        hdr.addWidget(_lbl(
            "オプション",
            f"font-size:15px; font-weight:700; color:{TEXT_PRI}; background:transparent; border:none;",
        ))
        hdr.addStretch()
        layout.addLayout(hdr)

        self._cb_run_ocr = QCheckBox("OCRを実行してテキストを埋め込む")
        self._cb_run_ocr.setChecked(True)
        self._cb_run_ocr.setStyleSheet(_CB_STYLE)

        self._cb_sort_name = QCheckBox("ファイル名順に並べ替え")
        self._cb_sort_name.setChecked(True)
        self._cb_sort_name.setStyleSheet(_CB_STYLE)

        layout.addWidget(self._cb_run_ocr)
        layout.addWidget(self._cb_sort_name)
        layout.addWidget(self._make_contrast_section())
        layout.addWidget(self._make_resize_section())
        return card

    def _make_contrast_section(self) -> QWidget:
        """Checkbox + brightness/gamma spinboxes for image contrast adjustment."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        self._cb_contrast = QCheckBox("画像のコントラストを調整")
        self._cb_contrast.setChecked(True)
        self._cb_contrast.setStyleSheet(_CB_STYLE)
        v.addWidget(self._cb_contrast)

        # Params row — indented under the checkbox
        self._contrast_params = QWidget()
        self._contrast_params.setStyleSheet("background: transparent;")
        self._contrast_params.setEnabled(False)
        row = QHBoxLayout(self._contrast_params)
        row.setContentsMargins(28, 0, 0, 0)
        row.setSpacing(8)

        row.addWidget(_lbl(
            "明るさ",
            f"font-size:12px; color:{TEXT_SEC}; background:transparent; border:none;",
        ))
        self._spin_brightness = QSpinBox()
        self._spin_brightness.setRange(-100, 100)
        self._spin_brightness.setValue(20)
        self._spin_brightness.setFixedWidth(64)
        self._spin_brightness.setStyleSheet(_SPINBOX_STYLE)
        row.addWidget(self._spin_brightness)

        row.addSpacing(8)
        row.addWidget(_lbl(
            "ガンマ",
            f"font-size:12px; color:{TEXT_SEC}; background:transparent; border:none;",
        ))
        self._spin_gamma = QDoubleSpinBox()
        self._spin_gamma.setRange(0.1, 5.0)
        self._spin_gamma.setSingleStep(0.1)
        self._spin_gamma.setDecimals(1)
        self._spin_gamma.setValue(1.6)
        self._spin_gamma.setFixedWidth(64)
        self._spin_gamma.setStyleSheet(_SPINBOX_STYLE)
        row.addWidget(self._spin_gamma)

        row.addStretch()
        v.addWidget(self._contrast_params)

        self._cb_contrast.toggled.connect(self._contrast_params.setEnabled)
        return container

    def _make_resize_section(self) -> QWidget:
        """Two checkbox+spinbox rows for width and height resize targets."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        self._cb_resize_w, self._spin_resize_w = self._make_resize_row("横幅を揃える", 1080, v)
        self._cb_resize_h, self._spin_resize_h = self._make_resize_row("縦幅を揃える", 1920, v)
        return container

    def _make_resize_row(
        self, label: str, default_px: int, layout: QVBoxLayout
    ) -> tuple[QCheckBox, QSpinBox]:
        """Return a (checkbox, spinbox) pair and append the row widget to layout."""
        row_widget = QWidget()
        row_widget.setStyleSheet("background: transparent;")
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        cb = QCheckBox(label)
        cb.setStyleSheet(_CB_STYLE)
        row.addWidget(cb)

        spin = QSpinBox()
        spin.setRange(1, 9999)
        spin.setValue(default_px)
        spin.setFixedWidth(72)
        spin.setEnabled(False)
        spin.setStyleSheet(_SPINBOX_STYLE)
        row.addWidget(spin)

        row.addWidget(_lbl(
            "px", f"font-size:12px; color:{TEXT_SEC}; background:transparent; border:none;"
        ))
        row.addStretch()

        cb.toggled.connect(spin.setEnabled)
        layout.addWidget(row_widget)
        return cb, spin

    def _make_run_section(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._run_btn = QPushButton("▶   PDF を生成する")
        self._run_btn.setFixedHeight(56)
        self._run_btn.setCursor(Qt.PointingHandCursor)
        self._run_btn.setStyleSheet(f"""
            QPushButton {{
                background: {CORAL}; color: white;
                border: none; border-radius: 14px;
                font-size: 16px; font-weight: 700;
            }}
            QPushButton:hover {{ background: #ff5252; }}
            QPushButton:pressed {{ background: #e53e3e; }}
            QPushButton:disabled {{ background: {BORDER_LIGHT}; color: {TEXT_MUTED}; }}
        """)
        self._run_btn.clicked.connect(self._on_run_clicked)

        self._progress_card = ProgressCard()

        layout.addWidget(self._run_btn)
        layout.addWidget(self._progress_card)
        return container

    # ── Slots ──────────────────────────────────────────────────────────────────

    def _on_run_clicked(self) -> None:
        self.run_requested.emit(RunOptions(
            output_dir=self._output_card.output_dir,
            output_name=self._output_card.output_name,
            sort_by_name=self._cb_sort_name.isChecked(),
            run_ocr=self._cb_run_ocr.isChecked(),
            contrast_adjust=self._cb_contrast.isChecked(),
            brightness=self._spin_brightness.value(),
            gamma=self._spin_gamma.value(),
            resize_width=self._spin_resize_w.value() if self._cb_resize_w.isChecked() else None,
            resize_height=self._spin_resize_h.value() if self._cb_resize_h.isChecked() else None,
        ))
