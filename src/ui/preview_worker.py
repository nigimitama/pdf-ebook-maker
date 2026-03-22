"""PreviewWorker — background thread that processes up to 10 sample images."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image
from PySide6.QtCore import QThread, Signal

from image_processing import resize_image, transform_intensity

from .run_options import RunOptions


@dataclass
class PreviewSample:
    path: str
    before: np.ndarray   # BGR or grayscale
    after: np.ndarray    # BGR or grayscale
    after_bytes: int     # JPEG size after processing


class PreviewWorker(QThread):
    """Load + process sample images and emit results."""

    finished = Signal(list, float)  # list[PreviewSample], estimated_mb
    error = Signal(str)

    def __init__(
        self,
        paths: list[str],
        options: RunOptions,
        total_count: int,
    ) -> None:
        super().__init__()
        self._paths = paths
        self._options = options
        self._total_count = total_count

    def run(self) -> None:
        try:
            samples: list[PreviewSample] = []
            for path in self._paths:
                before = _load(path)
                after = _apply(before, self._options)
                after_bytes = _jpeg_size(after, self._options.jpeg_quality)
                samples.append(PreviewSample(path, before, after, after_bytes))

            avg_bytes = sum(s.after_bytes for s in samples) / len(samples) if samples else 0
            estimated_mb = avg_bytes * self._total_count / (1024 * 1024)
            self.finished.emit(samples, estimated_mb)
        except Exception as exc:
            self.error.emit(str(exc))


def _load(path: str) -> np.ndarray:
    with Image.open(path) as pil_img:
        img = np.array(pil_img)
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    return img


def _apply(img: np.ndarray, opts: RunOptions) -> np.ndarray:
    if opts.contrast_adjust:
        img = transform_intensity(img, brightness=opts.brightness, gamma=opts.gamma)
    if opts.resize_width or opts.resize_height:
        img = resize_image(
            img,
            target_width=opts.resize_width,
            target_height=opts.resize_height,
        )
    return img


def _jpeg_size(img: np.ndarray, quality: int) -> int:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return int(len(buf)) if ok else 0
