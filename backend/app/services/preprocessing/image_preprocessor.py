"""
backend/app/services/preprocessing/image_preprocessor.py

Conservative image preprocessing for passport document images.

Design goals:
  - Make OCR more reliable without damaging the image
  - Preserve the original for future forensic modules
  - Handle real-world inputs: phone photos, scans, screenshots

What we DO:
  - EXIF orientation correction
  - Downscale very large images (>4000px) to reduce OCR latency
  - Mild CLAHE contrast enhancement for dark/flat images
  - Convert to RGB for PaddleOCR input

What we do NOT do:
  - Aggressive noise removal (can destroy text detail)
  - Binarisation (damages coloured security features)
  - Rotation correction (PaddleOCR angle_cls handles this better)
  - Cropping (we must retain the full layout for field localisation)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

# Maximum dimension (width or height) before we downscale
_MAX_DIMENSION = 4000
# Minimum dimension — warn if smaller (may degrade OCR quality)
_MIN_DIMENSION = 200


@dataclass
class PreprocessedImage:
    """Output of the preprocessing pipeline."""
    image_np: np.ndarray   # BGR numpy array ready for OCR
    original_size: tuple[int, int]   # (width, height) before any resize
    processed_size: tuple[int, int]  # (width, height) after resize
    was_downscaled: bool


def preprocess(image_np_bgr: np.ndarray) -> PreprocessedImage:
    """
    Apply conservative preprocessing to a passport image.

    Args:
        image_np_bgr: BGR numpy array from document ingestion.

    Returns:
        PreprocessedImage with the processed array and metadata.
    """
    h, w = image_np_bgr.shape[:2]
    original_size = (w, h)

    if w < _MIN_DIMENSION or h < _MIN_DIMENSION:
        logger.warning(
            "Image is very small (%dx%d). OCR quality may be poor.", w, h
        )

    # Step 1: EXIF orientation is already handled during ingestion (PIL convert)
    # so the array arriving here should already be correctly oriented.
    img = image_np_bgr.copy()

    # Step 2: Downscale if either dimension exceeds the threshold
    was_downscaled = False
    max_dim = max(h, w)
    if max_dim > _MAX_DIMENSION:
        scale = _MAX_DIMENSION / max_dim
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        was_downscaled = True
        logger.info("Downscaled image from %dx%d to %dx%d", w, h, new_w, new_h)
        h, w = new_h, new_w

    # Step 3: Mild CLAHE contrast enhancement on the luminance channel only.
    # This helps with under-exposed phone photos without altering the colour balance.
    try:
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)

        # Clip limit = 2.0 is conservative; tile grid 8x8 is standard
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_channel = clahe.apply(l_channel)

        lab_enhanced = cv2.merge([l_channel, a_channel, b_channel])
        img = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)
    except Exception as exc:
        # CLAHE failure is non-fatal — continue with the unenhanced image
        logger.warning("CLAHE enhancement failed (non-fatal): %s", exc)

    processed_size = (w, h)

    logger.info(
        "Preprocessing complete: original=%s processed=%s downscaled=%s",
        original_size, processed_size, was_downscaled,
    )

    return PreprocessedImage(
        image_np=img,
        original_size=original_size,
        processed_size=processed_size,
        was_downscaled=was_downscaled,
    )
