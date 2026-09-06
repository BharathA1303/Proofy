"""
backend/app/services/forensics/image_quality.py

Module 3: Image Quality Assessment.

Determines whether an image is of sufficient quality for the downstream
forensic techniques (ELA, photo boundary, compression analysis) to produce
a meaningful signal. If not, Module 3 must report "insufficient_data"
rather than manufacture a forensic conclusion on a bad image.

Thresholding strategy (documented, not hidden):
  - Minimum dimension: passport images below 600px on the short side rarely
    carry enough detail for ELA/edge analysis to be reliable.
  - Blur: variance of the Laplacian is a standard, cheap focus measure.
    Below ~25 the image is very likely out of focus.
  - Brightness: mean pixel intensity outside [25, 230] indicates severe
    under/over-exposure where local error/edge signals become unreliable.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ── Thresholds (documented above) ──────────────────────────────────────────
MIN_DIMENSION_PX = 600
MIN_BLUR_VARIANCE = 25.0
MIN_BRIGHTNESS_MEAN = 25.0
MAX_BRIGHTNESS_MEAN = 230.0


@dataclass
class ImageQualityResult:
    status: str  # "adequate" | "insufficient"
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def assess_image_quality(image_np_bgr: np.ndarray) -> ImageQualityResult:
    """
    Assess whether an image is adequate for forensic analysis.

    This is a gate, not a forensic signal itself: it never contributes to
    the tampering assessment, it only decides whether to attempt one.
    """
    h, w = image_np_bgr.shape[:2]
    reasons: list[str] = []

    gray = cv2.cvtColor(image_np_bgr, cv2.COLOR_BGR2GRAY)
    blur_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness_mean = float(gray.mean())
    brightness_std = float(gray.std())

    if min(h, w) < MIN_DIMENSION_PX:
        reasons.append(
            f"Image resolution ({w}x{h}) is below the {MIN_DIMENSION_PX}px minimum "
            "required for reliable forensic analysis."
        )

    if blur_variance < MIN_BLUR_VARIANCE:
        reasons.append(
            f"Image appears too blurred (focus measure={blur_variance:.1f}) for "
            "reliable edge and compression analysis."
        )

    if brightness_mean < MIN_BRIGHTNESS_MEAN:
        reasons.append(
            f"Image is too dark (mean brightness={brightness_mean:.1f}) for "
            "reliable forensic analysis."
        )
    elif brightness_mean > MAX_BRIGHTNESS_MEAN:
        reasons.append(
            f"Image is too bright / overexposed (mean brightness={brightness_mean:.1f}) "
            "for reliable forensic analysis."
        )

    metrics = {
        "width": w,
        "height": h,
        "blur_variance": round(blur_variance, 2),
        "brightness_mean": round(brightness_mean, 2),
        "brightness_std": round(brightness_std, 2),
    }

    status = "insufficient" if reasons else "adequate"
    logger.info("Image quality assessment: status=%s reasons=%d", status, len(reasons))

    return ImageQualityResult(status=status, reasons=reasons, metrics=metrics)
