"""SettingsPanel — right panel with output settings, options, run button, and progress.

Responsibility: collect output configuration; surface run/progress state.
Does not know which files will be processed — the parent passes that context.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .constants import (
    BG_GRAY,
    BORDER,
    BORDER_LIGHT,
    CORAL,
    GREEN,
    INDIGO,
    TEXT_MUTED,
    TEXT_PRI,
    TEXT_SEC,
    WHITE,
)


@dataclass(frozen=True)
class RunOptions:
    """Immutable snapshot of the settings panel when the user clicks Run."""

    output_dir: str
    output_name: str
    fit_page: bool
    sort_by_name: bool
    run_ocr: bool


def _lbl(text: str, style: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(style)
    return lbl


def _card() -> tuple[QWidget, QVBoxLayout]:
    """Return a white rounded card widget and its pre-configured layout."""
    card = QWidget()
    card.setStyleSheet(f"""
        QWidget {{
            background: {WHITE};
            border-radius: 16px;
            border: 1px solid {BORDER};
        }}
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
        set_run_enabled(bool)         -- enable/disable the Run button.
        set_running(bool)             -- toggle busy state.
        set_progress(int, str, str)   -- update progress bar and status text.
    """

    run_requested = Signal(object)  # RunOptions

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background: {BG_GRAY};")
        self._setup_ui()

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_run_enabled(self, enabled: bool) -> None:
        """Enable or disable the Run button (e.g. when no files are selected)."""
        self._run_btn.setEnabled(enabled)

    def set_running(self, running: bool) -> None:
        """Toggle the busy state: disables Run button and shows activity."""
        self._run_btn.setEnabled(not running)

    def set_progress(self, value: int, message: str, note: str = "") -> None:
        """Update the progress bar (0–100), status dot, message, and note."""
        if value <= 0:
            state = "idle"
        elif value >= 100:
            state = "done"
        else:
            state = "running"
        self._apply_status(state, message, note)
        self._progress_bar.setValue(value)
        self._pct_label.setText(f"{value}%" if value > 0 else "")

    # ── UI construction ────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        layout.addWidget(self._make_output_card())
        layout.addWidget(self._make_options_card())
        layout.addStretch()
        layout.addWidget(self._make_run_section())

    def _make_output_card(self) -> QWidget:
        card, layout = _card()

        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        hdr.addWidget(_lbl("📂", f"font-size:16px; background:transparent; border:none;"))
        hdr.addWidget(_lbl("出力設定", f"font-size:15px; font-weight:700; color:{TEXT_PRI}; background:transparent; border:none;"))
        hdr.addStretch()
        layout.addLayout(hdr)

        layout.addWidget(_lbl("保存先フォルダ", f"font-size:13px; font-weight:600; color:{TEXT_SEC}; background:transparent; border:none;"))
        layout.addLayout(self._make_path_row())

        layout.addWidget(_lbl("出力ファイル名", f"font-size:13px; font-weight:600; color:{TEXT_SEC}; background:transparent; border:none;"))
        layout.addLayout(self._make_filename_row())

        return card

    def _make_path_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self._output_path = QLineEdit()
        self._output_path.setPlaceholderText("/path/to/output")
        self._output_path.setFixedHeight(40)
        self._output_path.setStyleSheet(f"""
            QLineEdit {{
                background: {BG_GRAY}; border: 1px solid {BORDER};
                border-radius: 8px; padding: 0 12px;
                font-size: 13px; color: {TEXT_SEC};
            }}
            QLineEdit:focus {{ border-color: {INDIGO}; }}
        """)

        browse_btn = QPushButton("📁  参照")
        browse_btn.setFixedHeight(40)
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.setStyleSheet(f"""
            QPushButton {{
                background: #F0F5FF; color: {INDIGO};
                border: none; border-radius: 8px;
                padding: 0 14px; font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background: #E0E7FF; }}
        """)
        browse_btn.clicked.connect(self._browse_output_dir)

        row.addWidget(self._output_path, stretch=1)
        row.addWidget(browse_btn)
        return row

    def _make_filename_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self._output_name = QLineEdit()
        self._output_name.setText("output_ebook")
        self._output_name.setFixedHeight(40)
        self._output_name.setStyleSheet(f"""
            QLineEdit {{
                background: {BG_GRAY}; border: 1px solid {BORDER};
                border-radius: 8px; padding: 0 12px;
                font-size: 13px; color: {TEXT_PRI};
            }}
            QLineEdit:focus {{ border-color: {INDIGO}; }}
        """)

        ext_badge = QLabel("PDF")
        ext_badge.setFixedSize(50, 40)
        ext_badge.setAlignment(Qt.AlignCenter)
        ext_badge.setStyleSheet(
            f"background: {CORAL}; color: white; border-radius: 8px; font-size: 11px; font-weight: 700;"
        )

        row.addWidget(self._output_name, stretch=1)
        row.addWidget(ext_badge)
        return row

    def _make_options_card(self) -> QWidget:
        card, layout = _card()

        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        hdr.addWidget(_lbl("⚙", f"font-size:16px; background:transparent; border:none;"))
        hdr.addWidget(_lbl("オプション", f"font-size:15px; font-weight:700; color:{TEXT_PRI}; background:transparent; border:none;"))
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
        layout.addWidget(self._run_btn)
        layout.addWidget(self._make_progress_card())
        return container

    def _make_progress_card(self) -> QWidget:
        card = QWidget()
        card.setStyleSheet(f"""
            QWidget {{
                background: {BG_GRAY}; border: 1px solid {BORDER}; border-radius: 12px;
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)

        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet(
            f"color: {BORDER_LIGHT}; font-size: 10px; background: transparent; border: none;"
        )
        self._status_text = QLabel("待機中")
        self._status_text.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {TEXT_SEC}; background: transparent; border: none;"
        )
        self._pct_label = QLabel("")
        self._pct_label.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {CORAL}; background: transparent; border: none;"
        )

        status_row.addWidget(self._status_dot)
        status_row.addWidget(self._status_text)
        status_row.addStretch()
        status_row.addWidget(self._pct_label)
        layout.addLayout(status_row)

        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{ background: {BORDER}; border-radius: 4px; border: none; }}
            QProgressBar::chunk {{ background: {CORAL}; border-radius: 4px; }}
        """)
        layout.addWidget(self._progress_bar)

        self._status_note = QLabel("")
        self._status_note.setStyleSheet(
            f"font-size: 12px; color: {TEXT_MUTED}; background: transparent; border: none;"
        )
        layout.addWidget(self._status_note)
        return card

    # ── Slots ──────────────────────────────────────────────────────────────────

    def _on_run_clicked(self) -> None:
        self.run_requested.emit(
            RunOptions(
                output_dir=self._output_path.text().strip(),
                output_name=self._output_name.text().strip(),
                fit_page=self._cb_fit_page.isChecked(),
                sort_by_name=self._cb_sort_name.isChecked(),
                run_ocr=self._cb_run_ocr.isChecked(),
            )
        )

    def _browse_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "保存先フォルダを選択")
        if path:
            self._output_path.setText(path)

    # ── Internal helpers ───────────────────────────────────────────────────────

    _DOT_COLORS = {"running": GREEN, "done": GREEN, "error": "#EF4444", "idle": BORDER_LIGHT}

    def _apply_status(self, state: str, message: str, note: str) -> None:
        color = self._DOT_COLORS.get(state, BORDER_LIGHT)
        self._status_dot.setStyleSheet(
            f"color: {color}; font-size: 10px; background: transparent; border: none;"
        )
        self._status_text.setText(message)
        self._status_note.setText(note)
