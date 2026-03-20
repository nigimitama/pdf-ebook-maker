"""PagePreviewDialog — side-by-side image and OCR text preview for a single page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .constants import BORDER_LIGHT, TEXT_MUTED, TEXT_PRI, WHITE


class PagePreviewDialog(QDialog):
    """Modal dialog showing a page image on the left and its OCR text on the right."""

    def __init__(
        self,
        path: str,
        page_index: int,
        ocr_lines: list,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._path = path
        self._page_index = page_index
        self._ocr_lines = ocr_lines
        self.setWindowTitle(f"p.{page_index + 1}  {Path(path).name}")
        self.setMinimumSize(880, 600)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._make_image_panel())
        splitter.addWidget(self._make_text_panel())
        splitter.setSizes([540, 340])

        layout.addWidget(splitter)

    def _make_image_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #222; }")

        px = QPixmap(self._path)
        lbl = QLabel()
        if px.isNull():
            lbl.setText("画像を読み込めませんでした")
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; background: #222;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            scaled = px.scaledToWidth(520, Qt.TransformationMode.SmoothTransformation)
            lbl.setPixmap(scaled)
            lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            lbl.setStyleSheet("background: #222; padding: 12px;")

        scroll.setWidget(lbl)
        return scroll

    def _make_text_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background: {WHITE};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        header = QLabel("OCR テキスト")
        header.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {TEXT_PRI}; background: transparent;"
        )
        layout.addWidget(header)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                font-size: 12px;
                color: {TEXT_PRI};
                background: {WHITE};
                border: 1px solid {BORDER_LIGHT};
                border-radius: 6px;
                padding: 6px;
            }}
        """)

        if self._ocr_lines:
            lines = [r.text.strip() for r in self._ocr_lines if r.text.strip()]
            text_edit.setPlainText("\n".join(lines))
        else:
            text_edit.setPlaceholderText("OCRテキストがありません")
            text_edit.setStyleSheet(
                text_edit.styleSheet()
                + f"QTextEdit {{ color: {TEXT_MUTED}; }}"
            )

        layout.addWidget(text_edit, stretch=1)
        return panel
