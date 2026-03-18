"""MainWindow — top-level window that assembles panels and coordinates them.

Responsibility: compose HeaderBar, FilePanel, SettingsPanel, StructurePanel;
wire their signals; manage the two-phase OCR → Structure edit → PDF flow.

Phase 1 (OCR):
    FilePanel.files_changed  →  _on_files_changed  →  _start_ocr (auto)
    OcrWorker.ocr_done       →  _on_ocr_done       →  StructurePanel.load()

Phase 2 (PDF generation):
    SettingsPanel.pdf_requested  →  _on_pdf_btn_clicked  →  PdfWorker (QThread)

When OCR is disabled (run_ocr=False) the structure editor is skipped and PDF
generation starts immediately with an empty structure.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QMessageBox, QVBoxLayout, QWidget

from .constants import BG_GRAY
from .file_panel import FilePanel
from .header_bar import HeaderBar
from .model_preloader import ModelPreloader
from .ocr_worker import OcrWorker
from .pdf_worker import PdfWorker
from .run_options import RunOptions
from .settings_panel import SettingsPanel
from .structure_panel import StructurePanel


class MainWindow(QMainWindow):
    """Root window that assembles and coordinates all UI panels."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PDF Ebook Maker")
        self.setMinimumSize(1640, 780)
        self._worker: OcrWorker | None = None
        self._pdf_worker: PdfWorker | None = None
        self._preloader: ModelPreloader | None = None
        self._current_files: list[str] = []
        self._current_opts: RunOptions | None = None
        self._current_image_paths: list[str] = []
        self._current_ocr_results: dict[str, list] = {}
        self._setup_ui()

    # ── UI construction ────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        central.setStyleSheet(f"QWidget#central {{ background: {BG_GRAY}; }}")
        self.setCentralWidget(central)

        self._file_panel = FilePanel()
        self._settings_panel = SettingsPanel()
        self._structure_panel = StructurePanel()

        self._file_panel.files_changed.connect(self._on_files_changed)
        self._settings_panel.pdf_requested.connect(self._on_pdf_btn_clicked)
        self._structure_panel.export_requested.connect(self._on_export_requested)
        self._settings_panel.set_run_enabled(False)

        self._body_layout = QHBoxLayout()
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)
        self._body_layout.addWidget(self._file_panel)
        self._body_layout.addWidget(self._structure_panel)
        self._body_layout.addWidget(self._settings_panel, stretch=1)

        body = QWidget()
        body.setStyleSheet(f"background: {BG_GRAY};")
        body.setLayout(self._body_layout)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(HeaderBar())
        root.addWidget(body, stretch=1)

    # ── Model preloading ───────────────────────────────────────────────────────

    def _start_preload(self) -> None:
        from ocr import OCREngine  # noqa: PLC0415

        if not OCREngine.is_available():
            return
        self._preloader = ModelPreloader()
        self._preloader.status.connect(
            lambda msg: self._file_panel.set_progress(0, msg, "")
        )
        self._preloader.finished.connect(
            lambda: self._file_panel.set_progress(0, "OCRモデルの準備完了", "")
        )
        self._preloader.start()

    # ── Phase 1: OCR ──────────────────────────────────────────────────────────

    def _on_files_changed(self, files: list[str]) -> None:
        self._current_files = files
        if files and self._preloader is None:
            self._start_preload()
        # Auto-start OCR when files are added (skip if already running)
        if files and (self._worker is None or not self._worker.isRunning()):
            self._start_ocr()

    def _start_ocr(self) -> None:
        """Start OCR on the current file list."""
        opts = self._settings_panel.get_options()
        self._current_opts = opts
        self._settings_panel.set_running(True)
        self._file_panel.set_progress(0, "処理を開始します...", "")

        if not opts.run_ocr:
            # Skip OCR — go straight to PDF with an empty structure.
            from pdf import collect_image_paths  # noqa: PLC0415
            from document_structure import DocumentStructure  # noqa: PLC0415
            image_paths = collect_image_paths(
                list(self._current_files), sort_by_name=opts.sort_by_name
            )
            structure = DocumentStructure(pages=[], toc_entries=[])
            self._start_pdf_worker(image_paths, {}, structure, opts)
            return

        engine = (
            self._preloader.engine
            if self._preloader is not None and self._preloader.isFinished()
            else None
        )
        self._worker = OcrWorker(list(self._current_files), opts, engine=engine)
        self._worker.progress.connect(self._file_panel.set_progress)
        self._worker.ocr_done.connect(self._on_ocr_done)
        self._worker.finished.connect(self._on_ocr_worker_finished)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_ocr_done(self, image_paths: list[str], ocr_results: dict[str, list]) -> None:
        """OCR completed — build structure and populate Step 2."""
        from document_structure import build_structure  # noqa: PLC0415

        self._current_image_paths = image_paths
        self._current_ocr_results = ocr_results

        structure = build_structure(image_paths, ocr_results)

        if structure.suggested_title:
            self._settings_panel.set_suggested_output_name(structure.suggested_title)

        self._structure_panel.load(structure)
        self._settings_panel.set_running(False)
        self._file_panel.set_progress(90, "OCR完了 — 文書構造を確認してください", "")

    def _on_ocr_worker_finished(self) -> None:
        pass  # _on_ocr_done handles the transition.

    # ── Phase 2: PDF generation ───────────────────────────────────────────────

    def _on_pdf_btn_clicked(self) -> None:
        """User clicked PDF を生成する in Step 3."""
        opts = self._settings_panel.get_options()
        if not opts.output_dir:
            self._file_panel.set_progress(0, "保存先を指定してください", "")
            return
        self._current_opts = opts
        structure = self._structure_panel.current_structure
        self._settings_panel.set_running(True)
        self._file_panel.set_progress(0, "PDF生成中...", "")
        self._start_pdf_worker(
            self._current_image_paths,
            self._current_ocr_results,
            structure,
            self._current_opts,
        )

    def _on_export_requested(self, structure) -> None:
        if self._current_opts is None:
            return
        self._settings_panel.set_running(True)
        self._file_panel.set_progress(0, "PDF生成中...", "")
        self._start_pdf_worker(
            self._current_image_paths,
            self._current_ocr_results,
            structure,
            self._current_opts,
        )

    def _start_pdf_worker(
        self,
        image_paths: list[str],
        ocr_results: dict[str, list],
        structure,
        opts: RunOptions,
    ) -> None:
        self._pdf_worker = PdfWorker(image_paths, ocr_results, structure, opts)
        self._pdf_worker.progress.connect(self._file_panel.set_progress)
        self._pdf_worker.finished.connect(self._on_pdf_finished)
        self._pdf_worker.error.connect(self._on_worker_error)
        self._pdf_worker.start()

    def _on_pdf_finished(self) -> None:
        self._settings_panel.set_running(False)
        self._file_panel.set_progress(100, "完了！", "")

    # ── Common error handling ─────────────────────────────────────────────────

    def _on_worker_error(self, message: str) -> None:
        self._settings_panel.set_running(False)
        self._file_panel.set_progress(0, "エラーが発生しました", message)
        QMessageBox.critical(self, "エラー", message)
