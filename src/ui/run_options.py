"""RunOptions — immutable snapshot of PDF generation settings."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunOptions:
    """Immutable snapshot of the settings panel when the user clicks Run."""

    output_dir: str
    output_name: str
    sort_by_name: bool
    run_ocr: bool
    contrast_adjust: bool = False
    brightness: int = 20
    gamma: float = 1.6
    resize_width: int | None = None   # None = disabled
    resize_height: int | None = None  # None = disabled
