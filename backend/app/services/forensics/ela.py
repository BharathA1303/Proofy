"""
backend/app/services/forensics/ela.py

Module 3: Error Level Analysis (ELA).

Concept:
  Original Image -> JPEG recompression at a fixed quality -> pixel-level
  difference -> per-block error magnitude -> flag blocks whose error is
  statistically elevated relative to the image's own baseline.

IMPORTANT — what ELA is and is not:
  Re-saving a JPEG produces a different error signature in regions that were
  already compressed at a different quality than the rest of the image
  (e.g. a pasted-in region from a different source, or a region edited and
  re-saved). This is a genuine forensic signal, but high local error also
  occurs naturally at hard edges, fine text, and high-frequency textures
  (security patterns, MRZ text). ELA output is therefore an INDICATOR to be
  combined with other signals, never a standalone forgery verdict.

Determinism:
  The JPEG quality used for recompression is fixed (see ELA_JPEG_QUALITY),
  and no randomness is used anywhere in this module, so results are
  reproducible for the same input image.

Thresholding strategy (documented, not hidden):
  - The image is split into a fixed grid of blocks (BLOCK_SIZE px).
  - Per-block mean error is compared against the image-wide mean + K * std.
  - K = 2.5 was chosen conservatively (flags clear statistical outliers,
    not ordinary texture variance) for this prototype; it is not tuned
    against a labelled tampering dataset and should be revisited before
    any production use.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ── Configuration (documented above) ───────────────────────────────────────
ELA_JPEG_QUALITY = 90
BLOCK_SIZE = 32
OUTLIER_K = 2.5
# Fraction of image area flagged as anomalous before we call the result
# "suspicious" rather than "normal".
SUSPICIOUS_AREA_RATIO = 0.02
HIGH_CONCERN_AREA_RATIO = 0.08


@dataclass
class ELARegion:
    x: int
    y: int
    width: int
    height: int
    mean_error: float


@dataclass
class ELAResult:
    status: str  # "normal" | "suspicious"
    severity: str  # "low" | "medium" | "high"
    confidence: float
    mean_error: float
    max_error: float
    std_error: float
    flagged_area_ratio: float
    regions: list[ELARegion] = field(default_factory=list)
    description: str = ""


def _recompress_and_diff(image_np_bgr: np.ndarray, quality: int) -> np.ndarray:
    """Recompress the image as JPEG at `quality` and return the per-pixel error map (grayscale)."""
    success, encoded = cv2.imencode(".jpg", image_np_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not success:
        raise RuntimeError("JPEG recompression failed during ELA.")

    recompressed = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    diff = cv2.absdiff(image_np_bgr, recompressed)
    gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    return gray_diff


def run_ela(image_np_bgr: np.ndarray) -> ELAResult:
    """
    Run deterministic Error Level Analysis on the original image.

    Returns an ELAResult describing global error statistics and any
    blocks whose local error is a statistical outlier relative to the
    rest of the image.
    """
    h, w = image_np_bgr.shape[:2]
    error_map = _recompress_and_diff(image_np_bgr, ELA_JPEG_QUALITY)

    mean_error = float(error_map.mean())
    max_error = float(error_map.max())
    std_error = float(error_map.std())
    threshold = mean_error + OUTLIER_K * std_error

    regions: list[ELARegion] = []
    flagged_pixels = 0

    for y in range(0, h, BLOCK_SIZE):
        for x in range(0, w, BLOCK_SIZE):
            block = error_map[y:min(y + BLOCK_SIZE, h), x:min(x + BLOCK_SIZE, w)]
            block_mean = float(block.mean())
            if block_mean > threshold and block_mean > 5.0:
                regions.append(ELARegion(
                    x=x, y=y,
                    width=block.shape[1], height=block.shape[0],
                    mean_error=round(block_mean, 2),
                ))
                flagged_pixels += block.size

    flagged_area_ratio = flagged_pixels / (h * w) if h * w else 0.0

    if flagged_area_ratio >= HIGH_CONCERN_AREA_RATIO:
        status, severity = "suspicious", "high"
        description = (
            f"Error Level Analysis found elevated local compression error across "
            f"{flagged_area_ratio * 100:.1f}% of the image area, well above the "
            "statistical baseline for this document. This is an indicator, not proof, "
            "of localized editing."
        )
    elif flagged_area_ratio >= SUSPICIOUS_AREA_RATIO:
        status, severity = "suspicious", "medium"
        description = (
            f"Error Level Analysis found localized regions ({flagged_area_ratio * 100:.1f}% "
            "of image area) with compression error above the image's statistical baseline. "
            "This can indicate localized editing, but can also occur naturally at sharp "
            "edges, text, or printed security patterns."
        )
    else:
        status, severity = "normal", "low"
        description = (
            "Error Level Analysis did not find compression error patterns significantly "
            "different from the image's own baseline."
        )

    # Confidence reflects how reliable this measurement is, NOT the probability of forgery.
    confidence = round(min(0.95, 0.5 + std_error / 40.0), 2)

    logger.info(
        "ELA complete: mean=%.2f max=%.2f std=%.2f flagged_ratio=%.4f regions=%d",
        mean_error, max_error, std_error, flagged_area_ratio, len(regions),
    )

    # Cap the number of reported regions to keep the response compact —
    # keep the highest-error ones.
    regions.sort(key=lambda r: r.mean_error, reverse=True)
    top_regions = regions[:10]

    return ELAResult(
        status=status,
        severity=severity,
        confidence=confidence,
        mean_error=round(mean_error, 3),
        max_error=round(max_error, 3),
        std_error=round(std_error, 3),
        flagged_area_ratio=round(flagged_area_ratio, 4),
        regions=top_regions,
        description=description,
    )
