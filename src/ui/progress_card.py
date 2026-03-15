"""ProgressCard — progress display widget with status dot, message, and bar.

Responsibility: pure display; accepts updates via ``set_progress()``.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from .constants import BG_GRAY, BORDER, BORDER_LIGHT, CORAL, GREEN, TEXT_MUTED, TEXT_SEC

_DOT_COLORS: dict[str, str] = {
    "running": GREEN,
    "done": GREEN,
    "error": "#EF4444",
    "idle": BORDER_LIGHT,
}


class ProgressCard(QWidget):
    """Displays a status dot, message, progress bar, and supplementary note."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            ProgressCard {{
                background: {BG_GRAY}; border: 1px solid {BORDER}; border-radius: 12px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        layout.addLayout(self._make_status_row())
        layout.addWidget(self._make_progress_bar())
        layout.addWidget(self._make_note_label())

    def set_progress(self, value: int, message: str, note: str = "") -> None:
        """Update the progress bar (0–100), status dot colour, message, and note."""
        state = "idle" if value <= 0 else ("done" if value >= 100 else "running")
        color = _DOT_COLORS.get(state, BORDER_LIGHT)
        self._status_dot.setStyleSheet(
            f"color: {color}; font-size: 10px; background: transparent; border: none;"
        )
        self._status_text.setText(message)
        self._status_note.setText(note)
        self._progress_bar.setValue(value)
        self._pct_label.setText(f"{value}%" if value > 0 else "")

    # ── UI construction ────────────────────────────────────────────────────────

    def _make_status_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
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
        row.addWidget(self._status_dot)
        row.addWidget(self._status_text)
        row.addStretch()
        row.addWidget(self._pct_label)
        return row

    def _make_progress_bar(self) -> QProgressBar:
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{ background: {BORDER}; border-radius: 4px; border: none; }}
            QProgressBar::chunk {{ background: {CORAL}; border-radius: 4px; }}
        """)
        return self._progress_bar

    def _make_note_label(self) -> QLabel:
        self._status_note = QLabel("")
        self._status_note.setStyleSheet(
            f"font-size: 12px; color: {TEXT_MUTED}; background: transparent; border: none;"
        )
        return self._status_note
