"""RotationPreviewWorker — background thread that applies rotation to sample images for preview."""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image
from PySide6.QtCore import QThread, Signal

from .preview_worker import PreviewSample


class RotationPreviewWorker(QThread):
    """全画像の傾き角度を推定し、補正量の大きい上位N件をプレビュー用に生成するワーカー。

    Phase 1: 全画像について傾き角度のみ推定（OCR結果のbboxを使用）。
    Phase 2: 傾きが大きい順にソートして補正前後の画像を生成。

    Signals:
        progress(int, str): (percent 0–100, message)
        finished(list[PreviewSample], float): サンプルデータと推定サイズ（常に0）
        error(str): エラーメッセージ
    """

    progress = Signal(int, str)
    finished = Signal(list, float)
    error = Signal(str)

    def __init__(self, paths: list[str], ocr_results: dict[str, list]) -> None:
        super().__init__()
        self._paths = paths
        self._ocr_results = ocr_results

    def run(self) -> None:
        try:
            from image_processing.rotation import correct_skew, rotate_image  # noqa: PLC0415

            total = len(self._paths)

            # ── Phase 1: estimate angle for every image ────────────────────────
            entries: list[tuple[float, float, str, np.ndarray]] = []  # (abs_angle, angle, path, rgb)
            for i, path in enumerate(self._paths):
                pct = int(i / total * 50)
                self.progress.emit(pct, f"角度を推定中 ({i + 1}/{total})")
                img = np.array(Image.open(path).convert("RGB"))
                bboxes = [line.bbox for line in self._ocr_results.get(path, [])]
                _, angle = correct_skew(img, bboxes)
                entries.append((abs(angle), angle, path, img))

            # ── Phase 2: generate before/after sorted by |angle| desc ─────────
            # Re-use the angle estimated in Phase 1 to avoid calling correct_skew twice.
            entries.sort(key=lambda t: t[0], reverse=True)

            samples: list[PreviewSample] = []
            for j, (_, angle, path, before_rgb) in enumerate(entries):
                pct = 50 + int((j + 1) / len(entries) * 50)
                self.progress.emit(pct, f"プレビュー生成中 ({j + 1}/{len(entries)})")

                before_bgr = cv2.cvtColor(before_rgb, cv2.COLOR_RGB2BGR)
                after_rgb = rotate_image(before_rgb, angle) if abs(angle) >= 0.05 else before_rgb
                after_bgr = cv2.cvtColor(after_rgb, cv2.COLOR_RGB2BGR)

                ok, buf = cv2.imencode(".jpg", after_bgr, [cv2.IMWRITE_JPEG_QUALITY, 75])
                after_bytes = int(len(buf)) if ok else 0

                samples.append(PreviewSample(path, before_bgr, after_bgr, after_bytes, angle=angle))

            self.finished.emit(samples, 0.0)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
