"""OutputCard — output directory and filename configuration widget.

Responsibility: collect and expose output_dir / output_name; know nothing
about how they are used.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .constants import BG_GRAY, BORDER, CORAL, INDIGO, TEXT_PRI, TEXT_SEC, WHITE


def _lbl(text: str, style: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(style)
    return lbl


class OutputCard(QWidget):
    """Card widget for configuring output directory and filename.

    Properties:
        output_dir (str):  currently entered save directory path.
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
    def output_dir(self) -> str:
        return self._output_path.text().strip()

    @property
    def output_name(self) -> str:
        return self._output_name.text().strip()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build(self, layout: QVBoxLayout) -> None:
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        hdr.addWidget(_lbl("📂", "font-size:16px; background:transparent; border:none;"))
        hdr.addWidget(_lbl(
            "出力設定",
            f"font-size:15px; font-weight:700; color:{TEXT_PRI}; background:transparent; border:none;",
        ))
        hdr.addStretch()
        layout.addLayout(hdr)

        layout.addWidget(_lbl(
            "保存先フォルダ",
            f"font-size:13px; font-weight:600; color:{TEXT_SEC}; background:transparent; border:none;",
        ))
        layout.addLayout(self._make_path_row())

        layout.addWidget(_lbl(
            "出力ファイル名",
            f"font-size:13px; font-weight:600; color:{TEXT_SEC}; background:transparent; border:none;",
        ))
        layout.addLayout(self._make_filename_row())

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
            f"background: {CORAL}; color: white; border-radius: 8px;"
            " font-size: 11px; font-weight: 700;"
        )

        row.addWidget(self._output_name, stretch=1)
        row.addWidget(ext_badge)
        return row

    def _browse_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "保存先フォルダを選択")
        if path:
            self._output_path.setText(path)
