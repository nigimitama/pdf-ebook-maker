"""MainWindow — top-level window that assembles panels and coordinates them.

Responsibility: compose HeaderBar, FilePanel, SettingsPanel; wire their signals.
Contains no UI details — only orchestration logic.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QVBoxLayout, QWidget

from .constants import BG_GRAY
from .file_panel import FilePanel
from .header_bar import HeaderBar
from .settings_panel import RunOptions, SettingsPanel


class MainWindow(QMainWindow):
    """Root window that assembles and coordinates all UI panels.

    Signal flow:
        FilePanel.files_changed  →  _on_files_changed  →  SettingsPanel.set_run_enabled
        SettingsPanel.run_requested  →  _on_run_requested  →  (future: PDF worker)
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PDF Ebook Maker")
        self.setMinimumSize(1100, 780)
        self._setup_ui()

    # ── UI construction ────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        central.setStyleSheet(f"QWidget#central {{ background: {BG_GRAY}; }}")
        self.setCentralWidget(central)

        self._file_panel = FilePanel()
        self._settings_panel = SettingsPanel()

        # Wire inter-panel signals
        self._file_panel.files_changed.connect(self._on_files_changed)
        self._settings_panel.run_requested.connect(self._on_run_requested)

        # Run button starts disabled until files are selected
        self._settings_panel.set_run_enabled(False)

        body = QWidget()
        body.setStyleSheet(f"background: {BG_GRAY};")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self._file_panel)
        body_layout.addWidget(self._settings_panel, stretch=1)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(HeaderBar())
        root.addWidget(body, stretch=1)

    # ── Signal handlers ────────────────────────────────────────────────────────

    def _on_files_changed(self, files: list[str]) -> None:
        """Enable the Run button only when at least one file is selected."""
        self._settings_panel.set_run_enabled(len(files) > 0)

    def _on_run_requested(self, opts: RunOptions) -> None:
        """Validate options, then kick off PDF generation."""
        if not opts.output_dir:
            self._settings_panel.set_progress(0, "保存先を指定してください")
            return

        self._settings_panel.set_running(True)
        self._settings_panel.set_progress(0, "処理を開始します...", "")

        # TODO: start a QThread-based PDF worker here; connect its progress
        #       signal to self._settings_panel.set_progress() and its
        #       finished signal to self._settings_panel.set_running(False).
