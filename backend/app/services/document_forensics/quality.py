"""
backend/app/services/document_forensics/quality.py

Multi-Dimensional Document Image Quality Assessment Engine.
Evaluates resolution, focus/blur, illumination, contrast, and noise levels.
Enforces the critical boundary: IMAGE QUALITY PROBLEM != FORGERY.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from app.services.document_forensics.schema import (
    ForensicFinding,
    ImageQualityAssessment,
    SignalSeverity,
    SignalStatus,
    SignalType,
)

logger = logging.getLogger(__name__)

# Default baseline quality thresholds
DEFAULT_MIN_DIMENSION_PX = 450
DEFAULT_MIN_BLUR_VARIANCE = 25.0
DEFAULT_MIN_BRIGHTNESS_MEAN = 25.0
DEFAULT_MAX_BRIGHTNESS_MEAN = 230.0
DEFAULT_MIN_CONTRAST_STD = 15.0


class DocumentQualityEngine:
    """
    Evaluates physical capture quality of the document image.
    Acts as an entry gate: stops downstream forensics when an image
    is genuinely undecidable due to sensor defects or severe blur.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self.min_dimension = self.config.get("min_dimension", DEFAULT_MIN_DIMENSION_PX)
        self.min_blur = self.config.get("min_blur", DEFAULT_MIN_BLUR_VARIANCE)
        self.min_brightness = self.config.get("min_brightness", DEFAULT_MIN_BRIGHTNESS_MEAN)
        self.max_brightness = self.config.get("max_brightness", DEFAULT_MAX_BRIGHTNESS_MEAN)
        self.min_contrast = self.config.get("min_contrast", DEFAULT_MIN_CONTRAST_STD)

    def assess(self, image_np_bgr: np.ndarray) -> ImageQualityAssessment:
        """
        Execute comprehensive optical quality evaluation.

        Args:
            image_np_bgr: Decoded image in BGR format.

        Returns:
            ImageQualityAssessment dataclass.
        """
        h, w = image_np_bgr.shape[:2]
        reasons: List[str] = []

        # 1. Dimension Check
        if min(h, w) < self.min_dimension:
            reasons.append(
                f"Image resolution ({w}x{h}) is below the {self.min_dimension}px minimum "
                "required for reliable forensic analysis."
            )

        # 2. Gray conversion and metrics
        gray = cv2.cvtColor(image_np_bgr, cv2.COLOR_BGR2GRAY)

        # 3. Focus / Blur Measure (Variance of Laplacian)
        blur_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if blur_variance < self.min_blur:
            reasons.append(
                f"Image appears out of focus or blurred (focus metric={blur_variance:.1f} < {self.min_blur})."
            )

        # 4. Illumination / Brightness
        brightness_mean = float(gray.mean())
        if brightness_mean < self.min_brightness:
            reasons.append(
                f"Image is underexposed/too dark (mean brightness={brightness_mean:.1f} < {self.min_brightness})."
            )
        elif brightness_mean > self.max_brightness:
            reasons.append(
                f"Image is overexposed/too bright (mean brightness={brightness_mean:.1f} > {self.max_brightness})."
            )

        # 5. Contrast / Dynamic Range
        contrast_std = float(gray.std())
        if contrast_std < self.min_contrast:
            reasons.append(
                f"Image exhibits low contrast dynamic range (std={contrast_std:.1f} < {self.min_contrast})."
            )

        # 6. High-Frequency Noise Estimate (Residual after Median Filtering)
        median_filtered = cv2.medianBlur(gray, 3)
        noise_residual = cv2.absdiff(gray, median_filtered)
        noise_score = float(noise_residual.mean())

        aspect_ratio = float(w / max(1, h))
        is_adequate = len(reasons) == 0

        return ImageQualityAssessment(
            is_adequate=is_adequate,
            status="adequate" if is_adequate else "insufficient",
            width=w,
            height=h,
            aspect_ratio=aspect_ratio,
            blur_score=blur_variance,
            brightness_mean=brightness_mean,
            contrast_std=contrast_std,
            noise_score=noise_score,
            reasons=reasons,
        )

    def to_finding(self, quality: ImageQualityAssessment) -> ForensicFinding:
        """Translate quality assessment into a standard ForensicFinding item."""
        if not quality.is_adequate:
            status = SignalStatus.INSUFFICIENT_DATA
            severity = SignalSeverity.MEDIUM
            explanation = "Image quality is insufficient for reliable forensic evaluation: " + "; ".join(quality.reasons)
        else:
            status = SignalStatus.NORMAL
            severity = SignalSeverity.LOW
            explanation = "Image resolution, illumination, and focus meet forensic standards."

        return ForensicFinding(
            finding_id="quality_01",
            signal_type=SignalType.IMAGE_QUALITY,
            status=status,
            severity=severity,
            confidence=1.0,
            score=quality.blur_score,
            source="optical_quality_engine",
            explanation=explanation,
            metrics={
                "width": quality.width,
                "height": quality.height,
                "blur_score": quality.blur_score,
                "brightness": quality.brightness_mean,
                "contrast": quality.contrast_std,
                "noise": quality.noise_score,
            },
        )
