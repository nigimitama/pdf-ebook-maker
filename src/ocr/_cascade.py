"""Cascade text recognition — multi-model pipeline for line-image OCR.

Routes each text line through progressively wider PARSEQ models based on
the predicted character count, merging results in the original line order.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .parseq import PARSEQ


class _RecogLine:
    """Holds one detected text-line image and its recognition state."""

    __slots__ = ("npimg", "idx", "pred_char_cnt", "pred_str")

    def __init__(self, npimg: np.ndarray, idx: int, pred_char_cnt: float, pred_str: str = "") -> None:
        self.npimg = npimg
        self.idx = idx
        self.pred_char_cnt = pred_char_cnt
        self.pred_str = pred_str

    def __lt__(self, other: _RecogLine) -> bool:
        return self.idx < other.idx


def process_cascade(
    alllineobj: list[_RecogLine],
    recognizer30: PARSEQ,
    recognizer50: PARSEQ,
    recognizer100: PARSEQ,
) -> list[str]:
    """Run cascade recognition and return recognised strings in original line order."""
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
        targetdflistall, targetdflist50, targetdflist100 = _run_30(
            executor, recognizer30, targetdflist30, targetdflist50, targetdflistall
        )
        targetdflistall, targetdflist100 = _run_50(
            executor, recognizer50, targetdflist50, targetdflist100, targetdflistall
        )
        targetdflistall = _run_100(
            executor, recognizer100, targetdflist100, targetdflist200, targetdflistall
        )

    return [t.pred_str for t in sorted(targetdflistall)]


def _run_30(
    executor,
    recognizer: PARSEQ,
    targets: list[_RecogLine],
    overflow50: list[_RecogLine],
    done: list[_RecogLine],
) -> tuple[list[_RecogLine], list[_RecogLine], list[_RecogLine]]:
    results = list(executor.map(recognizer.read, [t.npimg for t in targets])) if targets else []
    for lineobj, pred_str in zip(targets, results):
        if len(pred_str) >= 25:
            overflow50.append(lineobj)
        else:
            lineobj.pred_str = pred_str
            done.append(lineobj)
    return done, overflow50, []


def _run_50(
    executor,
    recognizer: PARSEQ,
    targets: list[_RecogLine],
    overflow100: list[_RecogLine],
    done: list[_RecogLine],
) -> tuple[list[_RecogLine], list[_RecogLine]]:
    results = list(executor.map(recognizer.read, [t.npimg for t in targets])) if targets else []
    for lineobj, pred_str in zip(targets, results):
        if len(pred_str) >= 45:
            overflow100.append(lineobj)
        else:
            lineobj.pred_str = pred_str
            done.append(lineobj)
    return done, overflow100


def _run_100(
    executor,
    recognizer: PARSEQ,
    targets: list[_RecogLine],
    targets200: list[_RecogLine],
    done: list[_RecogLine],
) -> list[_RecogLine]:
    results = list(executor.map(recognizer.read, [t.npimg for t in targets])) if targets else []
    for lineobj, pred_str in zip(targets, results):
        lineobj.pred_str = pred_str
        if len(pred_str) >= 98 and lineobj.npimg.shape[0] < lineobj.npimg.shape[1]:
            base = lineobj.npimg
            half = base.shape[1] // 2
            targets200.append(_RecogLine(base[:, :half, :], lineobj.idx, 100))
            targets200.append(_RecogLine(base[:, half:, :], lineobj.idx, 100))
        else:
            done.append(lineobj)

    if targets200:
        results200 = list(executor.map(recognizer.read, [t.npimg for t in targets200]))
        for i in range(0, len(targets200) - 1, 2):
            merged = _RecogLine(None, targets200[i].idx, 100, results200[i] + results200[i + 1])
            done.append(merged)

    return done
