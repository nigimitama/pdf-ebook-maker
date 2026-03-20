"""OcrWorker — QThread that runs OCR and emits results for the structure editor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from PySide6.QtCore import QThread, Signal

from pdf import collect_image_paths

from .run_options import RunOptions


class OcrWorker(QThread):
    """バックグラウンドスレッドで OCR を実行するワーカー。

    PDF生成は行わない。OCR完了後に ocr_done を emit し、
    呼び出し元（MainWindow）が文書構造エディターへ移行する。

    Signals:
        progress(int, str, str): (percent 0–100, message, note)
        ocr_done(list[str], dict):  (ordered image_paths, ocr_results)
        finished():                 正常終了（ocr_done の後に emit）
        error(str):                 エラーメッセージ
    """

    progress = Signal(int, str, str)
    ocr_done = Signal(list, dict)   # list[str], dict[str, list]
    finished = Signal()
    error = Signal(str)

    def __init__(
        self,
        files: list[str],
        opts: RunOptions,
        engine: Any = None,
    ) -> None:
        super().__init__()
        self._files = files
        self._opts = opts
        self._engine = engine

    def run(self) -> None:
        try:
            image_paths = collect_image_paths(
                self._files, sort_by_name=self._opts.sort_by_name
            )
            if not image_paths:
                self.error.emit("処理できる画像ファイルが見つかりませんでした。")
                return

            ocr_results = self._run_ocr(image_paths)

            self.ocr_done.emit(image_paths, ocr_results)
            self.finished.emit()

        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))

    def _run_ocr(self, image_paths: list[str]) -> dict[str, list]:
        from image_processing import resize_image, transform_intensity  # noqa: PLC0415
        from ocr import OCREngine  # noqa: PLC0415

        engine = self._engine if self._engine is not None else OCREngine()
        engine.load_models(lambda msg: self.progress.emit(0, msg, ""))

        total = len(image_paths)
        results: dict[str, list] = {}
        for i, path in enumerate(image_paths):
            pct = int((i / total) * 90)
            self.progress.emit(pct, f"OCR処理中 ({i + 1}/{total})", Path(path).name)
            img_np = np.array(Image.open(path).convert("RGB"))
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
        self.progress.emit(100, "OCR完了", "")
        return results
