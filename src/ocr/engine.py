# Portions of this file are derived from ndlocr-lite/src/ocr.py
# Copyright (c) 2023, National Diet Library, Japan
# Released under CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/
# Source: https://github.com/ndl-lab/ndlocr-lite
# Modifications: restructured as a reusable Python class (OCREngine);
#                removed CLI argument parsing and file I/O;
#                added lazy model loading and progress callbacks.

"""OCR engine wrapping ndlocr-lite for local Japanese document OCR.

Usage example::

    from ocr import OCREngine, OcrResult

    engine = OCREngine()           # モデルは初回使用時にロード
    results = engine.run(image)    # image: np.ndarray (H, W, 3) RGB
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from yaml import safe_load

from .deim import DEIM
from .ndl_parser import convert_to_xml_string3
from .parseq import PARSEQ
from .reading_order.xy_cut.eval import eval_xml
from ._cascade import _RecogLine, process_cascade

sys.setrecursionlimit(5000)

_MODEL_DIR = Path(__file__).parent / "model"
_CONFIG_DIR = Path(__file__).parent / "config"

_DET_WEIGHTS = str(_MODEL_DIR / "deim-s-1024x1024.onnx")
_DET_CLASSES = str(_CONFIG_DIR / "ndl.yaml")
_REC_WEIGHTS_30 = str(_MODEL_DIR / "parseq-ndl-16x256-30-tiny-192epoch-tegaki3.onnx")
_REC_WEIGHTS_50 = str(_MODEL_DIR / "parseq-ndl-16x384-50-tiny-146epoch-tegaki2.onnx")
_REC_WEIGHTS_100 = str(_MODEL_DIR / "parseq-ndl-16x768-100-tiny-165epoch-tegaki2.onnx")
_REC_CLASSES = str(_CONFIG_DIR / "NDLmoji.yaml")


@dataclass
class OcrResult:
    """1行分のOCR結果。"""

    text: str
    bbox: tuple[int, int, int, int]  # (x, y, w, h) ピクセル座標
    confidence: float
    is_vertical: bool


class OCREngine:
    """ndlocr-lite を使って画像をOCRするエンジン。

    モデルは初回の :meth:`run` 呼び出し時に遅延ロードされる。
    """

    def __init__(self, device: str = "cpu") -> None:
        self.device = device
        self._detector: DEIM | None = None
        self._rec30: PARSEQ | None = None
        self._rec50: PARSEQ | None = None
        self._rec100: PARSEQ | None = None

    # ── Public API ──────────────────────────────────────────────────────────

    def load_models(self, progress_cb: Callable[[str], None] | None = None) -> None:
        """モデルを明示的にロードする。呼び出さなくても run() 時に自動ロードされる。"""
        if self._detector is not None:
            return
        _cb = progress_cb or (lambda msg: None)
        _cb("検出モデルをロード中...")
        self._detector = DEIM(
            model_path=_DET_WEIGHTS,
            class_mapping_path=_DET_CLASSES,
            score_threshold=0.2,
            conf_threshold=0.25,
            iou_threshold=0.2,
            device=self.device,
        )
        _cb("文字認識モデルをロード中...")
        charlist = self._load_charlist()
        self._rec30 = PARSEQ(_REC_WEIGHTS_30, charlist, device=self.device)
        self._rec50 = PARSEQ(_REC_WEIGHTS_50, charlist, device=self.device)
        self._rec100 = PARSEQ(_REC_WEIGHTS_100, charlist, device=self.device)
        _cb("モデルのロード完了")

    def run(
        self,
        image: np.ndarray,
        progress_cb: Callable[[str], None] | None = None,
    ) -> list[OcrResult]:
        """画像からテキストを認識して返す。

        Parameters
        ----------
        image:
            RGB順の numpy 配列 (H, W, 3) uint8。
        progress_cb:
            進捗メッセージを受け取るコールバック（省略可）。
        """
        if self._detector is None:
            self.load_models(progress_cb)

        _cb = progress_cb or (lambda msg: None)
        _cb("レイアウト解析中...")

        root, alllineobj = self._detect_lines(image)
        if not alllineobj:
            return []

        _cb(f"文字認識中... ({len(alllineobj)} 行)")
        recognized = process_cascade(alllineobj, self._rec30, self._rec50, self._rec100)
        _cb("OCR完了")
        return self._assemble_results(root, recognized)

    @staticmethod
    def is_available() -> bool:
        """OCRに必要なモデルファイルが存在するか確認する。"""
        return all(Path(p).exists() for p in [
            _DET_WEIGHTS, _REC_WEIGHTS_30, _REC_WEIGHTS_50, _REC_WEIGHTS_100,
            _REC_CLASSES, _DET_CLASSES,
        ])

    # ── Internal helpers ────────────────────────────────────────────────────

    def _detect_lines(self, image: np.ndarray) -> tuple[ET.Element, list[_RecogLine]]:
        """Run detector → XML → reading-order sort, return root and line objects."""
        img_h, img_w = image.shape[:2]
        detections = self._detector.detect(image)
        classeslist = list(self._detector.classes.values())

        resultobj: list = [dict(), dict()]
        resultobj[0][0] = []
        for i in range(17):
            resultobj[1][i] = []
        for det in detections:
            xmin, ymin, xmax, ymax = det["box"]
            if det["class_index"] == 0:
                resultobj[0][0].append([xmin, ymin, xmax, ymax])
            resultobj[1][det["class_index"]].append(
                [xmin, ymin, xmax, ymax, det["confidence"], det["pred_char_count"]]
            )

        xmlstr = convert_to_xml_string3(img_w, img_h, "page", classeslist, resultobj)
        root = ET.fromstring("<OCRDATASET>" + xmlstr + "</OCRDATASET>")
        eval_xml(root, logger=None)

        alllineobj = self._collect_line_images(image, root, detections)
        return root, alllineobj

    def _collect_line_images(
        self,
        image: np.ndarray,
        root: ET.Element,
        detections: list,
    ) -> list[_RecogLine]:
        """Extract per-line image crops from the layout XML."""
        alllineobj: list[_RecogLine] = []
        for idx, lineobj in enumerate(root.findall(".//LINE")):
            xmin = int(lineobj.get("X"))
            ymin = int(lineobj.get("Y"))
            line_w = int(lineobj.get("WIDTH"))
            line_h = int(lineobj.get("HEIGHT"))
            try:
                pred_char_cnt = float(lineobj.get("PRED_CHAR_CNT"))
            except (TypeError, ValueError):
                pred_char_cnt = 100.0
            lineimg = image[ymin:ymin + line_h, xmin:xmin + line_w, :]
            alllineobj.append(_RecogLine(lineimg, idx, pred_char_cnt))

        if not alllineobj and detections:
            alllineobj = self._fallback_detection_lines(image, root, detections)

        return alllineobj

    def _fallback_detection_lines(
        self,
        image: np.ndarray,
        root: ET.Element,
        detections: list,
    ) -> list[_RecogLine]:
        """Use raw detection boxes as LINE elements when layout analysis yields nothing."""
        page = root.find("PAGE")
        alllineobj: list[_RecogLine] = []
        for idx, det in enumerate(detections):
            xmin, ymin, xmax, ymax = det["box"]
            line_w, line_h = int(xmax - xmin), int(ymax - ymin)
            if line_w <= 0 or line_h <= 0:
                continue
            line_elem = ET.SubElement(page, "LINE")
            line_elem.set("TYPE", "本文")
            line_elem.set("X", str(int(xmin)))
            line_elem.set("Y", str(int(ymin)))
            line_elem.set("WIDTH", str(line_w))
            line_elem.set("HEIGHT", str(line_h))
            line_elem.set("CONF", f"{det['confidence']:0.3f}")
            pred_char_cnt = det.get("pred_char_count", 100.0)
            line_elem.set("PRED_CHAR_CNT", f"{pred_char_cnt:0.3f}")
            lineimg = image[int(ymin):int(ymax), int(xmin):int(xmax), :]
            alllineobj.append(_RecogLine(lineimg, idx, pred_char_cnt))
        return alllineobj

    @staticmethod
    def _assemble_results(root: ET.Element, recognized: list[str]) -> list[OcrResult]:
        """Combine layout XML and recognised strings into OcrResult objects."""
        results: list[OcrResult] = []
        for idx, lineobj in enumerate(root.findall(".//LINE")):
            if idx >= len(recognized):
                break
            xmin = int(lineobj.get("X"))
            ymin = int(lineobj.get("Y"))
            line_w = int(lineobj.get("WIDTH"))
            line_h = int(lineobj.get("HEIGHT"))
            try:
                conf = float(lineobj.get("CONF", 0))
            except (TypeError, ValueError):
                conf = 0.0
            results.append(OcrResult(
                text=recognized[idx],
                bbox=(xmin, ymin, line_w, line_h),
                confidence=conf,
                is_vertical=(line_h > line_w),
            ))
        return results

    @staticmethod
    def _load_charlist() -> list[str]:
        with open(_REC_CLASSES, encoding="utf-8") as f:
            charobj = safe_load(f)
        return list(charobj["model"]["charset_train"])
