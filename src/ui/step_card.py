"""StepCard — accordion card for one wizard step."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .constants import BORDER, CORAL, GREEN, TEXT_MUTED, TEXT_PRI, TEXT_SEC


class StepCard(QWidget):
    """Accordion card with locked / active / completed states.

    States
    ------
    locked    — gray border, muted title, lock icon, body hidden
    active    — coral border, dark title, chevron-down, body visible
    completed — green border, muted title, checkmark + status text, body hidden
    """

    def __init__(
        self,
        number: int,
        title: str,
        content: QWidget,
        collapsible: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._number = number
        self._title_text = title
        self._content = content
        self._collapsible = collapsible
        self._setup_ui()
        self.set_locked()

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_locked(self) -> None:
        self._badge.setText(str(self._number))
        self._badge.setStyleSheet(
            "background:#D1D5DB;color:white;border-radius:12px;"
            "font-size:12px;font-weight:bold;"
        )
        self._title_lbl.setStyleSheet(
            f"font-size:14px;font-weight:700;color:{TEXT_MUTED};"
        )
        self._status_lbl.setText("")
        self._content.setVisible(False)
        self._sep.setVisible(False)
        self.setStyleSheet(
            "StepCard{background:#FAFAFA;border-radius:12px;border:1px solid #E5E7EB;}"
        )

    def set_active(self) -> None:
        self._badge.setText(str(self._number))
        self._badge.setStyleSheet(
            f"background:{CORAL};color:white;border-radius:12px;"
            "font-size:12px;font-weight:bold;"
        )
        self._title_lbl.setStyleSheet(
            f"font-size:14px;font-weight:700;color:{TEXT_PRI};"
        )
        self._status_lbl.setText("")
        self._content.setVisible(True)
        self._sep.setVisible(True)
        self.setStyleSheet(
            f"StepCard{{background:white;border-radius:12px;border:2px solid {CORAL};}}"
        )

    def set_completed(self, status_text: str = "") -> None:
        self._badge.setText("✓")
        self._badge.setStyleSheet(
            f"background:{GREEN};color:white;border-radius:12px;"
            "font-size:12px;font-weight:bold;"
        )
        self._title_lbl.setStyleSheet(
            f"font-size:14px;font-weight:700;color:{TEXT_SEC};"
        )
        self._status_lbl.setText(status_text)
        if self._collapsible:
            self._content.setVisible(False)
            self._sep.setVisible(False)
        self.setStyleSheet(
            f"StepCard{{background:white;border-radius:12px;border:1px solid {GREEN};}}"
        )

    # ── UI construction ────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        hdr = QWidget()
        hdr.setStyleSheet("background:transparent;")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(16, 0, 16, 0)
        hdr_layout.setSpacing(12)

        self._badge = QLabel()
        self._badge.setFixedSize(24, 24)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr_layout.addWidget(self._badge)

        self._title_lbl = QLabel(self._title_text)
        self._title_lbl.setStyleSheet("background:transparent;")
        hdr_layout.addWidget(self._title_lbl)

        self._status_lbl = QLabel()
        self._status_lbl.setStyleSheet(
            f"font-size:12px;color:{GREEN};background:transparent;"
        )
        hdr_layout.addWidget(self._status_lbl)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        spacer.setStyleSheet("background:transparent;")
        hdr_layout.addWidget(spacer)


        hdr.setFixedHeight(52)
        layout.addWidget(hdr)

        self._sep = QWidget()
        self._sep.setFixedHeight(1)
        self._sep.setStyleSheet(f"background:{BORDER};")
        layout.addWidget(self._sep)

        layout.addWidget(self._content)
