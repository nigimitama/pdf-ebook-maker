"""OCR engine wrapping ndlocr-lite for local Japanese document OCR.

This module provides a high-level interface to run OCR on document images
using the NDL (National Diet Library) OCR models.

Usage example::

    from ocr import OCREngine, OcrResult

    engine = OCREngine()           # モデルは初回使用時にロード
    results = engine.run(image)    # image: np.ndarray (H, W, 3) RGB

    for r in results:
        print(r.text, r.bbox)
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image
from yaml import safe_load

# Local ndlocr-lite modules (copied into this package)
from .deim import DEIM
from .parseq import PARSEQ
from .ndl_parser import convert_to_xml_string3
from .reading_order.xy_cut.eval import eval_xml

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
    bbox: tuple[int, int, int, int]   # (x, y, w, h) ピクセル座標
    confidence: float
    is_vertical: bool


class _RecogLine:
    __slots__ = ("npimg", "idx", "pred_char_cnt", "pred_str")

    def __init__(self, npimg: np.ndarray, idx: int, pred_char_cnt: float, pred_str: str = ""):
        self.npimg = npimg
        self.idx = idx
        self.pred_char_cnt = pred_char_cnt
        self.pred_str = pred_str

    def __lt__(self, other: _RecogLine) -> bool:
        return self.idx < other.idx


def _process_cascade(
    alllineobj: list[_RecogLine],
    recognizer30: PARSEQ,
    recognizer50: PARSEQ,
    recognizer100: PARSEQ,
) -> list[str]:
    targetdflist30: list[_RecogLine] = []
    targetdflist50: list[_RecogLine] = []
    targetdflist100: list[_RecogLine] = []
    targetdflist200: list[_RecogLine] = []

    for lineobj in alllineobj:
        if lineobj.pred_char_cnt == 3:
            targetdflist30.append(lineobj)
        elif lineobj.pred_char_cnt == 2:
            targetdflist50.append(lineobj)
        else:
            targetdflist100.append(lineobj)

    targetdflistall: list[_RecogLine] = []
    with ThreadPoolExecutor(thread_name_prefix="ocr") as executor:
        resultlines30, resultlines50, resultlines100, resultlines200 = [], [], [], []
        if targetdflist30:
            resultlines30 = list(executor.map(recognizer30.read, [t.npimg for t in targetdflist30]))
        for i in range(len(targetdflist30)):
            pred_str = resultlines30[i]
            lineobj = targetdflist30[i]
            if len(pred_str) >= 25:
                targetdflist50.append(lineobj)
            else:
                lineobj.pred_str = pred_str
                targetdflistall.append(lineobj)

        if targetdflist50:
            resultlines50 = list(executor.map(recognizer50.read, [t.npimg for t in targetdflist50]))
        for i in range(len(targetdflist50)):
            pred_str = resultlines50[i]
            lineobj = targetdflist50[i]
            if len(pred_str) >= 45:
                targetdflist100.append(lineobj)
            else:
                lineobj.pred_str = pred_str
                targetdflistall.append(lineobj)

        if targetdflist100:
            resultlines100 = list(executor.map(recognizer100.read, [t.npimg for t in targetdflist100]))
        for i in range(len(targetdflist100)):
            pred_str = resultlines100[i]
            lineobj = targetdflist100[i]
            lineobj.pred_str = pred_str
            if len(pred_str) >= 98 and lineobj.npimg.shape[0] < lineobj.npimg.shape[1]:
                base = lineobj.npimg
                half = base.shape[1] // 2
                targetdflist200.append(_RecogLine(base[:, :half, :], lineobj.idx, 100))
                targetdflist200.append(_RecogLine(base[:, half:, :], lineobj.idx, 100))
            else:
                targetdflistall.append(lineobj)

        if targetdflist200:
            resultlines200 = list(executor.map(recognizer100.read, [t.npimg for t in targetdflist200]))
            for i in range(0, len(targetdflist200) - 1, 2):
                ia = targetdflist200[i]
                merged = _RecogLine(None, ia.idx, 100, resultlines200[i] + resultlines200[i + 1])
                targetdflistall.append(merged)

        targetdflistall = sorted(targetdflistall)
    return [t.pred_str for t in targetdflistall]


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

        Returns
        -------
        list[OcrResult]
            読み順に並んだ行ごとのOCR結果。
        """
        if self._detector is None:
            self.load_models(progress_cb)

        _cb = progress_cb or (lambda msg: None)
        _cb("レイアウト解析中...")

        img_h, img_w = image.shape[:2]
        img_name = "page"

        # ── 検出 ──────────────────────────────────────────────────────────
        detections = self._detector.detect(image)
        classeslist = list(self._detector.classes.values())

        resultobj: list = [dict(), dict()]
        resultobj[0][0] = list()
        for i in range(17):
            resultobj[1][i] = []

        for det in detections:
            xmin, ymin, xmax, ymax = det["box"]
            if det["class_index"] == 0:
                resultobj[0][0].append([xmin, ymin, xmax, ymax])
            resultobj[1][det["class_index"]].append(
                [xmin, ymin, xmax, ymax, det["confidence"], det["pred_char_count"]]
            )

        # ── XML構築 + 読み順ソート ──────────────────────────────────────
        xmlstr = convert_to_xml_string3(img_w, img_h, img_name, classeslist, resultobj)
        xmlstr = "<OCRDATASET>" + xmlstr + "</OCRDATASET>"
        root = ET.fromstring(xmlstr)
        eval_xml(root, logger=None)

        # ── 行画像の収集 ──────────────────────────────────────────────────
        alllineobj: list[_RecogLine] = []
        tatelinecnt = 0
        alllinecnt = 0

        for idx, lineobj in enumerate(root.findall(".//LINE")):
            xmin = int(lineobj.get("X"))
            ymin = int(lineobj.get("Y"))
            line_w = int(lineobj.get("WIDTH"))
            line_h = int(lineobj.get("HEIGHT"))
            try:
                pred_char_cnt = float(lineobj.get("PRED_CHAR_CNT"))
            except (TypeError, ValueError):
                pred_char_cnt = 100.0
            if line_h > line_w:
                tatelinecnt += 1
            alllinecnt += 1
            lineimg = image[ymin:ymin + line_h, xmin:xmin + line_w, :]
            alllineobj.append(_RecogLine(lineimg, idx, pred_char_cnt))

        # LINE 要素がないが検出がある場合は検出領域を LINE として扱う
        if len(alllineobj) == 0 and detections:
            page = root.find("PAGE")
            for idx, det in enumerate(detections):
                xmin, ymin, xmax, ymax = det["box"]
                line_w = int(xmax - xmin)
                line_h = int(ymax - ymin)
                if line_w > 0 and line_h > 0:
                    line_elem = ET.SubElement(page, "LINE")
                    line_elem.set("TYPE", "本文")
                    line_elem.set("X", str(int(xmin)))
                    line_elem.set("Y", str(int(ymin)))
                    line_elem.set("WIDTH", str(line_w))
                    line_elem.set("HEIGHT", str(line_h))
                    line_elem.set("CONF", f"{det['confidence']:0.3f}")
                    pred_char_cnt = det.get("pred_char_count", 100.0)
                    line_elem.set("PRED_CHAR_CNT", f"{pred_char_cnt:0.3f}")
                    if line_h > line_w:
                        tatelinecnt += 1
                    alllinecnt += 1
                    lineimg = image[int(ymin):int(ymax), int(xmin):int(xmax), :]
                    alllineobj.append(_RecogLine(lineimg, idx, pred_char_cnt))

        if not alllineobj:
            return []

        _cb(f"文字認識中... ({len(alllineobj)} 行)")

        # ── 文字認識 ──────────────────────────────────────────────────────
        recognized = _process_cascade(alllineobj, self._rec30, self._rec50, self._rec100)

        # ── 結果の組み立て ────────────────────────────────────────────────
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

        _cb("OCR完了")
        return results

    # ── Internal helpers ────────────────────────────────────────────────────

    @staticmethod
    def _load_charlist() -> list[str]:
        with open(_REC_CLASSES, encoding="utf-8") as f:
            charobj = safe_load(f)
        return list(charobj["model"]["charset_train"])

    @staticmethod
    def is_available() -> bool:
        """OCRに必要なモデルファイルが存在するか確認する。"""
        return (
            Path(_DET_WEIGHTS).exists()
            and Path(_REC_WEIGHTS_30).exists()
            and Path(_REC_WEIGHTS_50).exists()
            and Path(_REC_WEIGHTS_100).exists()
            and Path(_REC_CLASSES).exists()
            and Path(_DET_CLASSES).exists()
        )
