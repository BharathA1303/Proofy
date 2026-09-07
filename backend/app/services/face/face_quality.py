"""
backend/app/services/face/face_quality.py

Face quality assessment gate for document and live camera faces.

Guiding Principles:
  - No arbitrary percentage score without deterministic math.
  - Returns structured, explainable quality signals.
  - Disallows biometric comparison if quality is insufficient.
  - Generates clear, actionable officer / traveler instructions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class FaceQualityResult:
    status: str            # "acceptable" | "poor" | "unavailable"
    blur: str              # "acceptable" | "poor"
    brightness: str        # "acceptable" | "poor"
    contrast: str          # "acceptable" | "poor"
    face_size: str         # "acceptable" | "poor"
    pose: str              # "acceptable" | "poor"
    blur_score: float
    brightness_score: float
    contrast_score: float
    width: int
    height: int
    error_code: Optional[str] = None
    explanation: str = ""

    @property
    def is_acceptable(self) -> bool:
        return self.status == "acceptable"


def evaluate_face_quality(
    face_crop: np.ndarray,
    is_document: bool = False,
) -> FaceQualityResult:
    """
    Evaluate the quality of a cropped face image.

    Checks:
      1. Dimensions (face size >= settings.FACE_MIN_SIZE)
      2. Sharpness / Blur (Laplacian variance >= settings.FACE_MIN_LAPLACIAN_VAR)
      3. Brightness (mean grayscale in [settings.FACE_MIN_BRIGHTNESS, settings.FACE_MAX_BRIGHTNESS])
      4. Contrast (std dev of grayscale >= settings.FACE_MIN_CONTRAST)
      5. Aspect / Pose (aspect ratio width/height in [0.65, 1.45])

    Returns FaceQualityResult with deterministic status.
    """
    if face_crop is None or face_crop.size == 0:
        err = "DOCUMENT_FACE_QUALITY_INSUFFICIENT" if is_document else "LIVE_FACE_QUALITY_INSUFFICIENT"
        return FaceQualityResult(
            status="unavailable",
            blur="poor",
            brightness="poor",
            contrast="poor",
            face_size="poor",
            pose="poor",
            blur_score=0.0,
            brightness_score=0.0,
            contrast_score=0.0,
            width=0,
            height=0,
            error_code=err,
            explanation="Face crop is empty or unavailable.",
        )

    h, w = face_crop.shape[:2]

    # Convert to grayscale for metric evaluations
    if len(face_crop.shape) == 3 and face_crop.shape[2] == 3:
        gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
    else:
        gray = face_crop

    # 1. Blur / Sharpness via Laplacian Variance
    # Physical laminated cards / ID documents naturally have softer printed portrait dots
    min_laplacian = 15.0 if is_document else settings.FACE_MIN_LAPLACIAN_VAR
    laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    blur_acceptable = laplacian_var >= min_laplacian

    # 2. Brightness via Mean Luminance
    mean_brightness = float(np.mean(gray))
    too_dark = mean_brightness < settings.FACE_MIN_BRIGHTNESS
    too_bright = mean_brightness > settings.FACE_MAX_BRIGHTNESS
    brightness_acceptable = (not too_dark) and (not too_bright)

    # 3. Contrast via Standard Deviation
    contrast_val = float(np.std(gray))
    contrast_acceptable = contrast_val >= settings.FACE_MIN_CONTRAST

    # 4. Face Size
    min_face_dim = 50 if is_document else settings.FACE_MIN_SIZE
    size_acceptable = (w >= min_face_dim) and (h >= min_face_dim)

    # 5. Aspect Ratio / Alignment
    aspect = w / max(1, h)
    pose_acceptable = 0.60 <= aspect <= 1.50

    # Determine overall status and specific issue messaging
    reasons = []
    specific_error: Optional[str] = None

    if not size_acceptable:
        reasons.append(f"Face resolution too low ({w}x{h} < {min_face_dim}x{min_face_dim})")
        specific_error = "FACE_TOO_SMALL"
    elif too_dark:
        reasons.append(f"Image is too dark (brightness {mean_brightness:.1f} < {settings.FACE_MIN_BRIGHTNESS:.1f})")
        specific_error = "FACE_TOO_DARK"
    elif too_bright:
        reasons.append(f"Image is overexposed (brightness {mean_brightness:.1f} > {settings.FACE_MAX_BRIGHTNESS:.1f})")
        specific_error = "FACE_TOO_BRIGHT"
    elif not blur_acceptable:
        reasons.append(f"Image is blurry (Laplacian variance {laplacian_var:.1f} < {min_laplacian:.1f})")
        specific_error = "FACE_TOO_BLURRY"
    elif not pose_acceptable:
        reasons.append(f"Abnormal aspect/alignment (w/h ratio {aspect:.2f})")
        specific_error = "FACE_POORLY_ALIGNED"
    elif not contrast_acceptable:
        reasons.append(f"Low image contrast (std dev {contrast_val:.1f} < {settings.FACE_MIN_CONTRAST:.1f})")
        specific_error = "FACE_LOW_CONTRAST"


    is_all_acceptable = (
        size_acceptable
        and blur_acceptable
        and brightness_acceptable
        and contrast_acceptable
        and pose_acceptable
    )

    if is_all_acceptable:
        status = "acceptable"
        explanation = "Face image quality clears all biometric sharpness, lighting, and scale gates."
        error_code = None
    else:
        status = "poor"
        base_err = "DOCUMENT_FACE_QUALITY_INSUFFICIENT" if is_document else "LIVE_FACE_QUALITY_INSUFFICIENT"
        error_code = specific_error or base_err
        if is_document:
            explanation = f"Document photograph quality insufficient: {'; '.join(reasons)}."
        else:
            if too_dark:
                explanation = "Face image is too dark. Move to a better-lit position."
            elif too_bright:
                explanation = "Face image is overexposed. Adjust lighting or back away from glare."
            elif not blur_acceptable:
                explanation = "Face image is blurry. Please hold still during capture."
            elif not size_acceptable:
                explanation = "Face is too far away. Position closer to the camera."
            else:
                explanation = f"Live face quality insufficient: {'; '.join(reasons)}."

    logger.debug(
        "Face quality evaluated (is_document=%s): status=%s blur=%.1f brightness=%.1f contrast=%.1f size=%dx%d",
        is_document, status, laplacian_var, mean_brightness, contrast_val, w, h,
    )

    return FaceQualityResult(
        status=status,
        blur="acceptable" if blur_acceptable else "poor",
        brightness="acceptable" if brightness_acceptable else "poor",
        contrast="acceptable" if contrast_acceptable else "poor",
        face_size="acceptable" if size_acceptable else "poor",
        pose="acceptable" if pose_acceptable else "poor",
        blur_score=round(laplacian_var, 2),
        brightness_score=round(mean_brightness, 2),
        contrast_score=round(contrast_val, 2),
        width=w,
        height=h,
        error_code=error_code,
        explanation=explanation,
    )
