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

    def __init__(self, npimg: np.ndarray | None, idx: int, pred_char_cnt: float, pred_str: str = "") -> None:
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
    targets30: list[_RecogLine] = []
    targets50: list[_RecogLine] = []
    targets100: list[_RecogLine] = []

    for lineobj in alllineobj:
        if lineobj.pred_char_cnt == 3:
            targets30.append(lineobj)
        elif lineobj.pred_char_cnt == 2:
            targets50.append(lineobj)
        else:
            targets100.append(lineobj)

    done: list[_RecogLine] = []
    with ThreadPoolExecutor(thread_name_prefix="ocr") as executor:
        done, targets50 = _run_stage(executor, recognizer30, targets30, targets50, threshold=25, done=done)
        done, targets100 = _run_stage(executor, recognizer50, targets50, targets100, threshold=45, done=done)
        done = _run_wide_stage(executor, recognizer100, targets100, done)

    return [t.pred_str for t in sorted(done)]


def _run_stage(
    executor,
    recognizer: PARSEQ,
    targets: list[_RecogLine],
    overflow: list[_RecogLine],
    *,
    threshold: int,
    done: list[_RecogLine],
) -> tuple[list[_RecogLine], list[_RecogLine]]:
    """Run recognizer on targets; route lines longer than threshold to overflow for the next stage."""
    results = list(executor.map(recognizer.read, [t.npimg for t in targets])) if targets else []
    for lineobj, pred_str in zip(targets, results):
        if len(pred_str) >= threshold:
            overflow.append(lineobj)
        else:
            lineobj.pred_str = pred_str
            done.append(lineobj)
    return done, overflow


def _run_wide_stage(
    executor,
    recognizer: PARSEQ,
    targets: list[_RecogLine],
    done: list[_RecogLine],
) -> list[_RecogLine]:
    """Run the widest recognizer; split very long horizontal lines and merge the halves."""
    results = list(executor.map(recognizer.read, [t.npimg for t in targets])) if targets else []
    split_pairs: list[_RecogLine] = []

    for lineobj, pred_str in zip(targets, results):
        lineobj.pred_str = pred_str
        if lineobj.npimg is not None and len(pred_str) >= 98 and lineobj.npimg.shape[0] < lineobj.npimg.shape[1]:
            base = lineobj.npimg
            half = base.shape[1] // 2
            split_pairs.append(_RecogLine(base[:, :half, :], lineobj.idx, 100))
            split_pairs.append(_RecogLine(base[:, half:, :], lineobj.idx, 100))
        else:
            done.append(lineobj)

    if split_pairs:
        halves = list(executor.map(recognizer.read, [t.npimg for t in split_pairs]))
        for i in range(0, len(split_pairs) - 1, 2):
            merged = _RecogLine(None, split_pairs[i].idx, 100, halves[i] + halves[i + 1])
            done.append(merged)

    return done
