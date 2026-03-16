"""MainWindow — top-level window that assembles panels and coordinates them.

Responsibility: compose HeaderBar, FilePanel, SettingsPanel; wire their signals.
Contains no UI details — only orchestration logic.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QMessageBox, QVBoxLayout, QWidget

from .constants import BG_GRAY
from .file_panel import FilePanel
from .header_bar import HeaderBar
from .model_preloader import ModelPreloader
from .ocr_worker import OcrWorker
from .run_options import RunOptions
from .settings_panel import SettingsPanel


class MainWindow(QMainWindow):
    """Root window that assembles and coordinates all UI panels.

    Signal flow:
        FilePanel.files_changed      →  _on_files_changed   →  SettingsPanel.set_run_enabled
        SettingsPanel.run_requested  →  _on_run_requested   →  OcrWorker (QThread)
        ModelPreloader.status        →  SettingsPanel.set_progress  (startup only)
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PDF Ebook Maker")
        self.setMinimumSize(1100, 780)
        self._worker: OcrWorker | None = None
        self._preloader: ModelPreloader | None = None
        self._current_files: list[str] = []
        self._setup_ui()

    # ── UI construction ────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        central.setStyleSheet(f"QWidget#central {{ background: {BG_GRAY}; }}")
        self.setCentralWidget(central)

        self._file_panel = FilePanel()
        self._settings_panel = SettingsPanel()
        self._file_panel.files_changed.connect(self._on_files_changed)
        self._settings_panel.run_requested.connect(self._on_run_requested)
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

    # ── Model preloading ───────────────────────────────────────────────────────

    def _start_preload(self) -> None:
        """Start loading OCR models in the background immediately at startup."""
        from ocr import OCREngine  # noqa: PLC0415

        if not OCREngine.is_available():
            return
        self._preloader = ModelPreloader()
        self._preloader.status.connect(
            lambda msg: self._settings_panel.set_progress(0, msg, "")
        )
        self._preloader.finished.connect(
            lambda: self._settings_panel.set_progress(0, "OCRモデルの準備完了", "")
        )
        self._preloader.start()

    # ── Signal handlers ────────────────────────────────────────────────────────

    def _on_files_changed(self, files: list[str]) -> None:
        self._current_files = files
        self._settings_panel.set_run_enabled(len(files) > 0)
        if files and self._preloader is None:
            self._start_preload()

    def _on_run_requested(self, opts: RunOptions) -> None:
        if not opts.output_dir:
            self._settings_panel.set_progress(0, "保存先を指定してください")
            return

        self._settings_panel.set_running(True)
        self._settings_panel.set_progress(0, "処理を開始します...", "")

        # Use pre-loaded engine if ready; otherwise OcrWorker loads it on demand.
        engine = (
            self._preloader.engine
            if self._preloader is not None and self._preloader.isFinished()
            else None
        )

        self._worker = OcrWorker(list(self._current_files), opts, engine=engine)
        self._worker.progress.connect(self._settings_panel.set_progress)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_worker_finished(self) -> None:
        self._settings_panel.set_running(False)

    def _on_worker_error(self, message: str) -> None:
        self._settings_panel.set_running(False)
        self._settings_panel.set_progress(0, "エラーが発生しました", message)
        QMessageBox.critical(self, "エラー", message)
