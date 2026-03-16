"""ModelPreloader — eagerly loads OCR models in the background at startup.

Starts as soon as the application window is created so that model weights
are already in memory by the time the user clicks "Generate PDF".
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QThread, Signal


class ModelPreloader(QThread):
    """Background thread that loads OCR models and exposes the ready engine.

    Signals:
        status(str): human-readable progress messages during loading.
    """

    status = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._engine: Any = None

    @property
    def engine(self) -> Any:
        """The loaded OCREngine, or None if loading is not yet complete."""
        return self._engine

    def run(self) -> None:
        from ocr import OCREngine  # noqa: PLC0415

        if not OCREngine.is_available():
            return
        engine = OCREngine()
        engine.load_models(lambda msg: self.status.emit(msg))
        self._engine = engine
