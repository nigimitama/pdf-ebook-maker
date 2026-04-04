"""MainWindow — top-level window that assembles the wizard and coordinates workers.

Phase 1 (OCR):
    WizardPanel.ocr_requested    →  _start_ocr           →  OcrWorker (QThread)
    OcrWorker.ocr_done           →  _on_ocr_done         →  WizardPanel.on_ocr_done()

Phase 1.5 (Rotation correction):
    WizardPanel.rotation_requested →  _on_rotation_requested
      apply=True  →  RotationWorker  →  _on_rotation_done  →  _proceed_to_toc
      apply=False →  _proceed_to_toc (skip)

Phase 2 (PDF generation):
    WizardPanel.pdf_requested    →  _on_pdf_requested    →  PdfWorker (QThread)
    PdfWorker.finished           →  _on_pdf_finished     →  WizardPanel.on_pdf_done()
"""

from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QMessageBox, QVBoxLayout, QWidget

from .constants import BG_GRAY
from .header_bar import HeaderBar
from .model_preloader import ModelPreloader
from .ocr_worker import OcrWorker
from .pdf_worker import PdfWorker
from .run_options import RunOptions
from .wizard_panel import WizardPanel


class MainWindow(QMainWindow):
    """Root window that assembles and coordinates all UI panels."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PDF Ebook Maker")
        self.setMinimumSize(960, 780)
        self.resize(1060, 780)
        self._worker: OcrWorker | None = None
        self._rotation_worker = None
        self._pdf_worker: PdfWorker | None = None
        self._preloader: ModelPreloader | None = None
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

        self._wizard = WizardPanel()
        self._wizard.ocr_step_activated.connect(self._start_preload)
        self._wizard.ocr_requested.connect(self._start_ocr)
        self._wizard.rotation_requested.connect(self._on_rotation_requested)
        self._wizard.pdf_requested.connect(self._on_pdf_requested)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(HeaderBar())
        root.addWidget(self._wizard, stretch=1)

    # ── Model preloading ───────────────────────────────────────────────────────

    def _start_preload(self) -> None:
        from ocr import OCREngine  # noqa: PLC0415

        if self._preloader is not None or not OCREngine.is_available():
            return
        self._preloader = ModelPreloader()
        self._preloader.status.connect(
            lambda msg: self._wizard.set_ocr_progress(0, msg, "")
        )
        self._preloader.finished.connect(
            lambda: self._wizard.set_ocr_progress(0, "OCRモデルの準備完了", "")
        )
        self._preloader.start()

    # ── Phase 1: OCR ──────────────────────────────────────────────────────────

    def _start_ocr(self, opts: RunOptions) -> None:
        self._current_opts = opts
        self._wizard.set_running(True)
        self._wizard.set_ocr_progress(0, "処理を開始します...", "")

        engine = (
            self._preloader.engine
            if self._preloader is not None and self._preloader.isFinished()
            else None
        )
        self._worker = OcrWorker(
            list(self._wizard.current_files), opts, engine=engine
        )
        self._worker.progress.connect(self._wizard.set_ocr_progress)
        self._worker.ocr_done.connect(self._on_ocr_done)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_ocr_done(self, image_paths: list[str], ocr_results: dict[str, list]) -> None:
        self._current_image_paths = image_paths
        self._current_ocr_results = ocr_results
        self._wizard.on_ocr_done(image_paths, ocr_results)
        self._wizard.set_running(False)
        self._wizard.set_ocr_progress(100, "OCR完了", "")

    # ── Phase 1.5: Rotation correction ────────────────────────────────────────

    def _on_rotation_requested(self, apply_deskew: bool) -> None:
        if apply_deskew:
            from .rotation_worker import RotationWorker  # noqa: PLC0415

            self._wizard.set_running(True)
            self._wizard.set_rotation_progress(0, "傾き補正を開始します...", "")
            self._rotation_worker = RotationWorker(
                self._current_image_paths,
                self._current_ocr_results,
                angle_overrides=self._wizard.angle_overrides,
            )
            self._rotation_worker.progress.connect(self._wizard.set_rotation_progress)
            self._rotation_worker.rotation_done.connect(self._on_rotation_done)
            self._rotation_worker.error.connect(self._on_worker_error)
            self._rotation_worker.start()
        else:
            self._wizard.set_rotation_progress(100, "補正なし（スキップ）", "")
            self._proceed_to_toc(
                self._current_image_paths,
                self._current_ocr_results,
                was_corrected=False,
            )

    def _on_rotation_done(
        self, new_image_paths: list[str], path_mapping: dict[str, str]
    ) -> None:
        self._current_image_paths = new_image_paths
        self._current_ocr_results = {
            path_mapping.get(old, old): results
            for old, results in self._current_ocr_results.items()
        }
        self._wizard.set_running(False)
        self._proceed_to_toc(
            self._current_image_paths,
            self._current_ocr_results,
            was_corrected=True,
        )

    def _proceed_to_toc(
        self,
        image_paths: list[str],
        ocr_results: dict[str, list],
        was_corrected: bool,
    ) -> None:
        from document_structure import build_structure  # noqa: PLC0415

        structure = build_structure(image_paths, ocr_results)
        self._wizard.on_correction_done(structure, ocr_results, was_corrected)

    # ── Phase 2: PDF generation ────────────────────────────────────────────────

    def _on_pdf_requested(self) -> None:
        opts = self._wizard.current_options
        self._current_opts = opts
        structure = self._wizard.current_structure
        self._wizard.set_running(True)
        self._start_pdf_worker(
            self._current_image_paths,
            self._current_ocr_results,
            structure,
            opts,
        )

    def _start_pdf_worker(
        self,
        image_paths: list[str],
        ocr_results: dict[str, list],
        structure,
        opts: RunOptions,
    ) -> None:
        self._pdf_worker = PdfWorker(image_paths, ocr_results, structure, opts)
        self._pdf_worker.finished.connect(self._on_pdf_finished)
        self._pdf_worker.error.connect(self._on_worker_error)
        self._pdf_worker.start()

    def _on_pdf_finished(self) -> None:
        self._wizard.set_running(False)
        self._wizard.on_pdf_done()

    # ── Common error handling ──────────────────────────────────────────────────

    def _on_worker_error(self, message: str) -> None:
        self._wizard.set_running(False)
        self._wizard.on_error(message)
        QMessageBox.critical(self, "エラー", message)
