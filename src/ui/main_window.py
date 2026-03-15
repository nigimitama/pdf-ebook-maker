"""MainWindow — top-level window that assembles panels and coordinates them.

Responsibility: compose HeaderBar, FilePanel, SettingsPanel; wire their signals.
Contains no UI details — only orchestration logic.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QMessageBox, QVBoxLayout, QWidget

from .constants import BG_GRAY
from .file_panel import FilePanel
from .header_bar import HeaderBar
from .settings_panel import RunOptions, SettingsPanel


class _OcrWorker(QThread):
    """バックグラウンドスレッドで画像リストにOCRを実行するワーカー。

    Signals:
        progress(int, str, str): (percent 0-100, message, note)
        finished():              正常終了
        error(str):              エラーメッセージ
    """

    progress = Signal(int, str, str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, files: list[str], opts: RunOptions) -> None:
        super().__init__()
        self._files = files
        self._opts = opts

    def run(self) -> None:
        try:
            # 対象ファイルリストを展開
            image_paths = _collect_image_paths(self._files, self._opts.sort_by_name)
            if not image_paths:
                self.error.emit("処理できる画像ファイルが見つかりませんでした。")
                return

            total = len(image_paths)
            ocr_results: dict[str, list] = {}  # path → list[OcrResult]

            if self._opts.run_ocr:
                from ocr import OCREngine
                engine = OCREngine()

                def _ocr_progress(msg: str) -> None:
                    self.progress.emit(0, msg, "")

                engine.load_models(_ocr_progress)

                for i, path in enumerate(image_paths):
                    pct = int((i / total) * 80)
                    self.progress.emit(pct, f"OCR処理中 ({i+1}/{total})", Path(path).name)
                    pil_img = Image.open(path).convert("RGB")
                    img_np = np.array(pil_img)
                    ocr_results[path] = engine.run(img_np)

            self.progress.emit(85, "PDF生成中...", "")
            _build_pdf(image_paths, self._opts, ocr_results)
            self.progress.emit(100, "完了！", "")
            self.finished.emit()

        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


_SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}


def _collect_image_paths(sources: list[str], sort_by_name: bool) -> list[str]:
    """sources (ファイルまたはフォルダのパスリスト) から画像ファイルパスリストを作る。"""
    paths: list[str] = []
    for src in sources:
        p = Path(src)
        if p.is_dir():
            paths.extend(
                str(f) for f in p.iterdir()
                if f.is_file() and f.suffix.lower() in _SUPPORTED_EXTS
            )
        elif p.suffix.lower() in _SUPPORTED_EXTS:
            paths.append(str(p))
    if sort_by_name:
        paths.sort(key=lambda x: Path(x).name.lower())
    return paths


def _build_pdf(
    image_paths: list[str],
    opts: RunOptions,
    ocr_results: dict[str, list],
) -> None:
    """画像リストからPDFを生成する。OCR結果がある場合は不可視テキストレイヤーを埋め込む。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as rl_canvas

    out_path = str(Path(opts.output_dir) / (opts.output_name + ".pdf"))
    c = rl_canvas.Canvas(out_path)

    for path in image_paths:
        pil_img = Image.open(path).convert("RGB")
        img_w, img_h = pil_img.size

        if opts.fit_page:
            page_w, page_h = A4
        else:
            page_w, page_h = float(img_w), float(img_h)

        c.setPageSize((page_w, page_h))

        # スケール係数
        scale_x = page_w / img_w
        scale_y = page_h / img_h

        c.drawInlineImage(pil_img, 0, 0, width=page_w, height=page_h)

        # OCRテキストを不可視レイヤーとして埋め込む（テキスト描画モード3=invisible）
        results = ocr_results.get(path, [])
        if results:
            for r in results:
                x, y, w, h = r.bbox
                pdf_x = x * scale_x
                # reportlab はY軸が下から上なので変換
                pdf_y = page_h - (y + h) * scale_y
                font_size = max(4, int(h * scale_y * 0.9))
                tx = c.beginText(pdf_x, pdf_y)
                tx.setTextRenderMode(3)  # 3 = invisible (PDF spec §9.3.6)
                tx.setFont("Helvetica", font_size)
                tx.textLine(r.text)
                c.drawText(tx)

        c.showPage()

    c.save()


class MainWindow(QMainWindow):
    """Root window that assembles and coordinates all UI panels.

    Signal flow:
        FilePanel.files_changed  →  _on_files_changed  →  SettingsPanel.set_run_enabled
        SettingsPanel.run_requested  →  _on_run_requested  →  _OcrWorker (QThread)
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PDF Ebook Maker")
        self.setMinimumSize(1100, 780)
        self._worker: _OcrWorker | None = None
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
        self._current_files = files
        self._settings_panel.set_run_enabled(len(files) > 0)

    def _on_run_requested(self, opts: RunOptions) -> None:
        """Validate options, then kick off PDF generation in a worker thread."""
        if not opts.output_dir:
            self._settings_panel.set_progress(0, "保存先を指定してください")
            return

        self._settings_panel.set_running(True)
        self._settings_panel.set_progress(0, "処理を開始します...", "")

        self._worker = _OcrWorker(list(self._current_files), opts)
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
