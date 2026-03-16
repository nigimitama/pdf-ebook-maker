"""OcrWorker — QThread that orchestrates image collection, OCR, and PDF generation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtCore import QThread, Signal

from pdf import build_pdf, collect_image_paths

from .run_options import RunOptions


class OcrWorker(QThread):
    """バックグラウンドスレッドで OCR → PDF 生成を実行するワーカー。

    Signals:
        progress(int, str, str): (percent 0–100, message, note)
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
            image_paths = collect_image_paths(self._files, sort_by_name=self._opts.sort_by_name)
            if not image_paths:
                self.error.emit("処理できる画像ファイルが見つかりませんでした。")
                return

            ocr_results = self._run_ocr(image_paths) if self._opts.run_ocr else {}

            self.progress.emit(85, "PDF生成中...", "")
            output_path = str(Path(self._opts.output_dir) / (self._opts.output_name + ".pdf"))
            build_pdf(
                image_paths,
                output_path,
                ocr_results=ocr_results,
                contrast_adjust=self._opts.contrast_adjust,
                brightness=self._opts.brightness,
                gamma=self._opts.gamma,
                resize_width=self._opts.resize_width,
                resize_height=self._opts.resize_height,
            )
            self.progress.emit(100, "完了！", "")
            self.finished.emit()

        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))

    def _run_ocr(self, image_paths: list[str]) -> dict[str, list]:
        from image_processing import resize_image, transform_intensity  # noqa: PLC0415
        from ocr import OCREngine  # noqa: PLC0415

        engine = OCREngine()
        engine.load_models(lambda msg: self.progress.emit(0, msg, ""))

        total = len(image_paths)
        results: dict[str, list] = {}
        for i, path in enumerate(image_paths):
            pct = int((i / total) * 80)
            self.progress.emit(pct, f"OCR処理中 ({i + 1}/{total})", Path(path).name)
            img_np = np.array(Image.open(path).convert("RGB"))
            # Apply the same transforms used by build_pdf so OCR bboxes
            # are in the processed image's coordinate space.
            if self._opts.resize_width or self._opts.resize_height:
                img_np = resize_image(
                    img_np,
                    target_width=self._opts.resize_width,
                    target_height=self._opts.resize_height,
                )
            if self._opts.contrast_adjust:
                img_np = transform_intensity(
                    img_np,
                    brightness=self._opts.brightness,
                    gamma=self._opts.gamma,
                )
            results[path] = engine.run(img_np)
        return results
