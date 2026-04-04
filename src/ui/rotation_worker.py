"""RotationWorker — QThread that applies rotation correction to scanned images."""

from __future__ import annotations

import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtCore import QThread, Signal


def _process_one(
    args: tuple[int, str, str, list[tuple[int, int, int, int]], float | None],
) -> tuple[int, str, str]:
    """傾き推定・補正を1枚分実行する（スレッドプール向け純粋関数）。

    angle_override が指定されている場合はその角度で補正する（自動推定をスキップ）。

    Returns:
        (original_index, original_path, output_path)
    """
    from image_processing.rotation import correct_skew, rotate_image  # noqa: PLC0415

    i, path, temp_dir, bboxes, angle_override = args
    img = np.array(Image.open(path).convert("RGB"))

    if angle_override is not None:
        if abs(angle_override) < 0.05:
            return i, path, path
        corrected = rotate_image(img, angle_override)
    else:
        corrected, _ = correct_skew(img, bboxes)
        if corrected is img:
            return i, path, path

    new_path = str(Path(temp_dir) / f"rotated_{i:04d}.png")
    Image.fromarray(corrected).save(new_path)
    return i, path, new_path


class RotationWorker(QThread):
    """バックグラウンドスレッドで傾き補正を実行するワーカー。

    OCR結果のbboxから傾き角度を推定し、各画像に補正を適用して
    一時ディレクトリに保存する。傾き推定はスレッドプールで並列実行。

    Signals:
        progress(int, str, str): (percent 0–100, message, note)
        rotation_done(list[str], dict[str, str]): (new_image_paths, path_mapping)
        error(str): エラーメッセージ
    """

    progress = Signal(int, str, str)
    rotation_done = Signal(list, dict)  # list[str], dict[str, str]
    error = Signal(str)

    def __init__(
        self,
        image_paths: list[str],
        ocr_results: dict[str, list],
        angle_overrides: dict[str, float] | None = None,
    ) -> None:
        super().__init__()
        self._image_paths = image_paths
        self._ocr_results = ocr_results
        self._angle_overrides = angle_overrides or {}
        self._temp_dir = tempfile.mkdtemp(prefix="pdf_ebook_rotation_")

    def run(self) -> None:
        try:
            total = len(self._image_paths)
            args = [
                (
                    i,
                    p,
                    self._temp_dir,
                    _bboxes_for(self._ocr_results.get(p, [])),
                    self._angle_overrides.get(p),
                )
                for i, p in enumerate(self._image_paths)
            ]

            results: dict[int, tuple[str, str]] = {}
            done = 0

            with ProcessPoolExecutor() as executor:
                futures = {executor.submit(_process_one, a): a for a in args}
                for future in as_completed(futures):
                    i, orig_path, out_path = future.result()
                    results[i] = (orig_path, out_path)
                    done += 1
                    pct = int(done / total * 100)
                    self.progress.emit(pct, f"補正中 ({done}/{total})", Path(orig_path).name)

            new_paths = [results[i][1] for i in range(total)]
            path_mapping = {results[i][0]: results[i][1] for i in range(total)}

            self.progress.emit(100, "傾き補正完了", "")
            self.rotation_done.emit(new_paths, path_mapping)

        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


def _bboxes_for(ocr_lines: list) -> list[tuple[int, int, int, int]]:
    """OcrResult リストから (x, y, w, h) bbox のリストを取り出す。"""
    return [line.bbox for line in ocr_lines]
