"""
backend/app/services/preprocessing/image_preprocessor.py

Conservative image preprocessing for passport document images.

Design goals:
  - Make OCR more reliable without damaging the image
  - Preserve the original for future forensic modules
  - Handle real-world inputs: phone photos, scans, screenshots

What we DO:
  - EXIF orientation correction
  - Downscale only very large images to reduce OCR latency
  - Mild CLAHE contrast enhancement for dark/flat images
  - Convert to RGB for PaddleOCR input

What we do NOT do:
  - Aggressive noise removal (can destroy text detail)
  - Destructive binarisation of the primary image (damages coloured
    security features) — low-contrast documents instead get a stronger,
    non-destructive contrast boost (see _enhance_low_contrast)
  - Cropping (we must retain the full layout for field localisation)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

# Maximum dimension (width or height) before we downscale.
# ID documents carry small, dense text (MRZ lines, Aadhaar/PAN numbers) that
# needs real pixel density to survive OCR — 1600px was aggressive enough to
# blur small glyphs on high-DPI scans, so the ceiling is raised to 2600px.
_MAX_DIMENSION = 2600
# Minimum dimension — warn if smaller (may degrade OCR quality)
_MIN_DIMENSION = 200

# Deskewing configuration
_DESKEW_THUMBNAIL_MAX_DIM = 360
_MIN_SKEW_ANGLE_THRESHOLD = 0.8   # Minimum tilt to trigger rotation (degrees)
_MAX_SKEW_ANGLE_LIMIT = 30.0      # Safety cap: maximum supported rotation angle (degrees)


@dataclass
class PreprocessedImage:
    """Output of the preprocessing pipeline."""
    image_np: np.ndarray   # BGR numpy array ready for OCR
    original_size: tuple[int, int]   # (width, height) before any resize
    processed_size: tuple[int, int]  # (width, height) after resize
    was_downscaled: bool
    skew_angle: float = 0.0          # Skew angle in degrees corrected (0.0 if upright)


def detect_skew_angle(image_np_bgr: np.ndarray) -> float:
    """
    Rapidly detect document skew angle in degrees using edge analysis
    and probabilistic Hough line transformation on a downscaled thumbnail.

    Returns:
        Skew angle in degrees (e.g. +5.5 means rotated clockwise, needing
        counter-clockwise correction). Returns 0.0 if image is already upright
        or if insufficient horizontal lines are detected.
    """
    h, w = image_np_bgr.shape[:2]
    if h < 50 or w < 50:
        return 0.0

    try:
        # Convert to single-channel grayscale before resize for 3x faster memory throughput
        gray = cv2.cvtColor(image_np_bgr, cv2.COLOR_BGR2GRAY)
        max_dim = max(h, w)
        if max_dim > _DESKEW_THUMBNAIL_MAX_DIM:
            scale = _DESKEW_THUMBNAIL_MAX_DIM / max_dim
            small_gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_LINEAR)
        else:
            small_gray = gray

        edges = cv2.Canny(small_gray, 100, 200, apertureSize=3)

        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=50,
            minLineLength=30,
            maxLineGap=10,
        )
        if lines is None or len(lines) < 3:
            return 0.0

        angles: list[float] = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            dx = x2 - x1
            dy = y2 - y1
            if dx == 0:
                continue
            angle = float(np.degrees(np.arctan2(dy, dx)))
            if -_MAX_SKEW_ANGLE_LIMIT <= angle <= _MAX_SKEW_ANGLE_LIMIT:
                angles.append(angle)

        if len(angles) < 3:
            return 0.0

        median_angle = float(np.median(angles))
        if abs(median_angle) < _MIN_SKEW_ANGLE_THRESHOLD:
            return 0.0

        return median_angle
    except Exception as exc:
        logger.debug("Skew angle detection skipped on exception: %s", exc)
        return 0.0


def deskew_image(image_np_bgr: np.ndarray, angle: float) -> np.ndarray:
    """
    Rotate an image by the given angle (in degrees) to straighten it,
    expanding bounding borders to prevent clipping corner content and
    filling margins with neutral document white.
    """
    if abs(angle) < _MIN_SKEW_ANGLE_THRESHOLD:
        return image_np_bgr

    h, w = image_np_bgr.shape[:2]
    center = (w / 2, h / 2)

    # 2D affine rotation matrix
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos = np.abs(M[0, 0])
    sin = np.abs(M[0, 1])

    # Compute new bounding dimensions to preserve full document content
    new_w = int((h * sin) + (w * cos))
    new_h = int((h * cos) + (w * sin))

    # Adjust transformation matrix with translation
    M[0, 2] += (new_w / 2) - center[0]
    M[1, 2] += (new_h / 2) - center[1]

    # Warp with neutral white background (255, 255, 255) ideal for document OCR
    straightened = cv2.warpAffine(
        image_np_bgr,
        M,
        (new_w, new_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    return straightened


def preprocess(image_np_bgr: np.ndarray) -> PreprocessedImage:
    """
    Apply conservative, high-speed preprocessing to a document image.

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

    # Step 1: EXIF orientation is corrected during ingestion (ImageOps.exif_transpose)
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

    # Step 2.5: High-speed automated document deskewing (< 25ms overhead)
    skew_angle = detect_skew_angle(img)
    if abs(skew_angle) >= _MIN_SKEW_ANGLE_THRESHOLD:
        logger.info("Deskewing document: detected skew = %+.2f degrees", skew_angle)
        img = deskew_image(img, -skew_angle)
        h, w = img.shape[:2]

    # Step 3: CLAHE contrast enhancement on the luminance channel only.
    # Clip limit adapts to how flat/faded the source looks — faded photocopies
    # and low-contrast scans (common with older ID documents) need a stronger
    # pull than a normally-exposed phone photo, without altering colour balance.
    try:
        gray_for_contrast = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        contrast_std = float(gray_for_contrast.std())
        # Low std deviation == flat/low-contrast image; scale clip limit up to compensate.
        clip_limit = 3.5 if contrast_std < 40 else 2.0

        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)

        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
        l_channel = clahe.apply(l_channel)

        lab_enhanced = cv2.merge([l_channel, a_channel, b_channel])
        img = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)

        if contrast_std < 40:
            logger.info("Low-contrast source detected (std=%.1f) — applied stronger CLAHE (clip=%.1f)", contrast_std, clip_limit)
    except Exception as exc:
        # CLAHE failure is non-fatal — continue with the unenhanced image
        logger.warning("CLAHE enhancement failed (non-fatal): %s", exc)

    processed_size = (w, h)

    logger.info(
        "Preprocessing complete: original=%s processed=%s downscaled=%s skew_angle=%.2f",
        original_size, processed_size, was_downscaled, skew_angle,
    )

    return PreprocessedImage(
        image_np=img,
        original_size=original_size,
        processed_size=processed_size,
        was_downscaled=was_downscaled,
        skew_angle=skew_angle,
    )
