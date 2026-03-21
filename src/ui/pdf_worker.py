"""PdfWorker — QThread that builds the final PDF from OCR results and document structure."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from document_structure import DocumentStructure

from .run_options import RunOptions


class PdfWorker(QThread):
    """バックグラウンドスレッドで PDF を生成するワーカー。

    Signals:
        progress(int, str, str): (percent 0–100, message, note)
        finished():              正常終了
        error(str):              エラーメッセージ
    """

    progress = Signal(int, str, str)
    finished = Signal()
    error = Signal(str)

    def __init__(
        self,
        image_paths: list[str],
        ocr_results: dict[str, list],
        structure: DocumentStructure,
        opts: RunOptions,
    ) -> None:
        super().__init__()
        self._image_paths = image_paths
        self._ocr_results = ocr_results
        self._structure = structure
        self._opts = opts

    def run(self) -> None:
        try:
            from pdf import build_pdf  # noqa: PLC0415

            self.progress.emit(0, "PDF生成中...", "")
            output_path = str(
                Path(self._opts.output_dir) / (self._opts.output_name + ".pdf")
            )
            build_pdf(
                self._image_paths,
                output_path,
                ocr_results=self._ocr_results,
                toc_entries=self._structure.toc_entries,
                contrast_adjust=self._opts.contrast_adjust,
                brightness=self._opts.brightness,
                gamma=self._opts.gamma,
                resize_width=self._opts.resize_width,
                resize_height=self._opts.resize_height,
                jpeg_quality=self._opts.jpeg_quality,
            )
            self.progress.emit(100, "完了！", "")
            self.finished.emit()

        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
