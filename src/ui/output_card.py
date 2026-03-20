"""OutputCard — output filename configuration widget.

Responsibility: collect and expose output_name; know nothing about how it is used.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from .constants import BG_GRAY, BORDER, CORAL, INDIGO, TEXT_PRI, WHITE


def _lbl(text: str, style: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(style)
    return lbl


class OutputCard(QWidget):
    """Card widget for configuring the output filename (without extension).

    Properties:
        output_name (str): currently entered filename (without extension).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            OutputCard {{
                background: {WHITE}; border-radius: 16px; border: 1px solid {BORDER};
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        self._build(layout)

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def output_name(self) -> str:
        return self._output_name.text().strip()

    def set_output_name(self, name: str) -> None:
        """Update the filename field (called when a title is inferred from OCR)."""
        if name:
            self._output_name.setText(name)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build(self, layout: QVBoxLayout) -> None:
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        hdr.addWidget(_lbl("📄", "font-size:16px; background:transparent; border:none;"))
        hdr.addWidget(_lbl(
            "出力ファイル名",
            f"font-size:15px; font-weight:700; color:{TEXT_PRI}; background:transparent; border:none;",
        ))
        hdr.addStretch()
        layout.addLayout(hdr)

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
        ext_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ext_badge.setStyleSheet(
            f"background: {CORAL}; color: white; border-radius: 8px;"
            " font-size: 11px; font-weight: 700;"
        )

        row.addWidget(self._output_name, stretch=1)
        row.addWidget(ext_badge)
        layout.addLayout(row)

    # output_dir kept as empty string for backward compatibility
    @property
    def output_dir(self) -> str:
        return ""
