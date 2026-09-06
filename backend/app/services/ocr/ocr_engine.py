"""
backend/app/services/ocr/ocr_engine.py

Generic PaddleOCR engine wrapper.

Design decisions:
  - Singleton: the model is loaded ONCE at application startup via the lifespan
    event in main.py and stored in this module-level variable.
  - Generic: this class knows nothing about passport fields — it returns raw
    OCR regions that document-specific parsers can interpret.
  - Reusable: all future document types (Visa, DL, NID, etc.) will use this
    same engine with their own parser.

OCR Region shape returned:
  {
    "text":       str,
    "confidence": float (0.0–1.0),
    "bbox":       [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]  (4-point polygon)
  }
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class OCRRegion:
    """A single text detection+recognition result from PaddleOCR."""
    text: str
    confidence: float
    # Bounding polygon as list of [x, y] integer pairs
    bbox: list[list[int]] = field(default_factory=list)


# Module-level singleton — populated by init_engine() at app startup
_paddle_ocr_instance: Any = None


def init_engine(lang: str = "en", use_angle_cls: bool = True, use_gpu: bool = False) -> None:
    """
    Initialize the PaddleOCR model.

    Call this ONCE during application startup (FastAPI lifespan).
    Subsequent calls are no-ops (idempotent).

    Args:
        lang:           Language model to use.
        use_angle_cls:  Enable text orientation classification.
        use_gpu:        Use GPU acceleration (False for CPU-only deployment).
    """
    global _paddle_ocr_instance

    if _paddle_ocr_instance is not None:
        logger.debug("OCR engine already initialized — skipping.")
        return

    logger.info("Initializing PaddleOCR engine (lang=%s, gpu=%s)…", lang, use_gpu)
    try:
        from paddleocr import PaddleOCR  # local import — avoids issues when testing without paddle

        _paddle_ocr_instance = PaddleOCR(
            use_angle_cls=use_angle_cls,
            lang=lang,
            use_gpu=use_gpu,
            show_log=False,         # suppress PaddleOCR's internal verbose output
        )
        logger.info("PaddleOCR engine initialized successfully.")
    except Exception as exc:
        logger.critical("Failed to initialize PaddleOCR: %s", exc, exc_info=True)
        # Re-raise so the application startup fails visibly rather than silently
        raise RuntimeError(f"OCR engine initialization failed: {exc}") from exc


def is_ready() -> bool:
    """Return True if the OCR engine has been initialized."""
    return _paddle_ocr_instance is not None


def run_ocr(image_np: np.ndarray) -> list[OCRRegion]:
    """
    Run OCR on a preprocessed image and return all detected text regions.

    Args:
        image_np: BGR numpy array (OpenCV convention).

    Returns:
        List of OCRRegion objects ordered roughly top-to-bottom, left-to-right.

    Raises:
        RuntimeError: If the OCR engine has not been initialized.
        Exception:    On PaddleOCR inference failure (caller handles this).
    """
    if _paddle_ocr_instance is None:
        raise RuntimeError(
            "OCR engine is not initialized. Call init_engine() at application startup."
        )

    logger.info("Running OCR on image shape=%s", image_np.shape)

    # PaddleOCR expects BGR numpy array
    raw_results = _paddle_ocr_instance.ocr(image_np, cls=True)

    regions: list[OCRRegion] = []

    # PaddleOCR 2.x returns: [ [ [bbox, (text, conf)], ... ] ]
    # The outer list corresponds to pages (always 1 page for a single image)
    if not raw_results or raw_results[0] is None:
        logger.warning("PaddleOCR returned no results for this image.")
        return regions

    for line in raw_results[0]:
        if line is None:
            continue
        try:
            bbox_raw, (text, confidence) = line
            # Convert float bbox coordinates to int
            bbox_int = [[int(pt[0]), int(pt[1])] for pt in bbox_raw]
            regions.append(OCRRegion(
                text=text.strip(),
                confidence=float(confidence),
                bbox=bbox_int,
            ))
        except (TypeError, ValueError, IndexError) as exc:
            logger.warning("Skipping malformed OCR region: %s | raw=%s", exc, line)
            continue

    logger.info(
        "OCR completed: %d regions detected. Avg confidence: %.3f",
        len(regions),
        (sum(r.confidence for r in regions) / len(regions)) if regions else 0.0,
    )

    return regions
