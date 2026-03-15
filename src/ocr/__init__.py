"""OCR module using ndlocr-lite for local Japanese document OCR.

Quick start::

    from ocr import OCREngine, OcrResult

    engine = OCREngine()
    results = engine.run(image)   # image: np.ndarray (H, W, 3) RGB uint8
"""

from .engine import OCREngine, OcrResult

__all__ = ["OCREngine", "OcrResult"]
