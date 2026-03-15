"""SettingsPanel — right panel with output settings, options, run button, and progress.

Responsibility: collect PDF generation configuration; surface run/progress state.
Does not know which files will be processed — the parent passes that context.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .constants import BG_GRAY, BORDER, BORDER_LIGHT, CORAL, TEXT_MUTED, TEXT_PRI, WHITE
from .output_card import OutputCard
from .progress_card import ProgressCard
from .run_options import RunOptions

__all__ = ["RunOptions", "SettingsPanel"]


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

        cb_style = f"""
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
        self._cb_fit_page = QCheckBox("画像を自動的にページサイズに合わせる")
        self._cb_fit_page.setChecked(True)
        self._cb_fit_page.setStyleSheet(cb_style)

        self._cb_sort_name = QCheckBox("ファイル名順に並べ替え")
        self._cb_sort_name.setStyleSheet(cb_style)

        self._cb_run_ocr = QCheckBox("OCRを実行してテキストを埋め込む（日本語文書向け）")
        self._cb_run_ocr.setStyleSheet(cb_style)

        layout.addWidget(self._cb_fit_page)
        layout.addWidget(self._cb_sort_name)
        layout.addWidget(self._cb_run_ocr)
        return card

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
            fit_page=self._cb_fit_page.isChecked(),
            sort_by_name=self._cb_sort_name.isChecked(),
            run_ocr=self._cb_run_ocr.isChecked(),
        ))
