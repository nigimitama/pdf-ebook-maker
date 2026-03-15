"""HeaderBar — top application bar with logo, title, subtitle, and version badge.

Responsibility: pure display widget. No state, no business logic.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from .constants import BORDER, CORAL, INDIGO, TEXT_PRI, TEXT_SEC, WHITE


class HeaderBar(QWidget):
    """Displays the application icon, name, subtitle, and version badge."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(64)
        self.setStyleSheet(f"border-bottom: 1px solid {BORDER};")
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(12)

        icon = QLabel("📖")
        icon.setFixedSize(36, 36)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(f"background: {CORAL}; border-radius: 10px; font-size: 18px;")

        title = QLabel("PDF Ebook Maker")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRI};")

        subtitle = QLabel("複数画像からPDFを生成")
        subtitle.setStyleSheet(f"font-size: 13px; color: {TEXT_SEC};")

        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addStretch()
