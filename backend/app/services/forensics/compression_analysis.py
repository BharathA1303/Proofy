"""
backend/app/services/forensics/compression_analysis.py

Module 3: Local Compression Inconsistency Analysis.

Concept:
  Different regions of a genuine, single-source document (photograph, MRZ
  text band, background security pattern) are compressed together and tend
  to share a similar "blockiness" signature. A region spliced in from a
  different source/quality often carries a measurably different signature.

IMPORTANT:
  Different regions of a LEGITIMATE document can also show different
  compression characteristics — a photo has different frequency content
  than printed text or a security pattern, and scanning/printing pipelines
  are not perfectly uniform. This analysis reports a comparative indicator
  only; it never concludes tampering by itself.

Blockiness metric:
  A simplified version of the standard JPEG blockiness measure: the mean
  absolute pixel difference across 8x8 block boundaries, compared to the
  mean absolute difference between adjacent pixels *within* blocks. A
  region compressed at a very different quality shows a different ratio.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Relative difference in blockiness score between regions before we call
# it a notable inconsistency. Chosen conservatively to accommodate natural
# frequency differences between smooth portrait photos and high-contrast text.
INCONSISTENCY_RATIO_SUSPICIOUS = 5.0
INCONSISTENCY_RATIO_HIGH = 10.0

JPEG_BLOCK = 8


@dataclass
class RegionBox:
    x: int
    y: int
    width: int
    height: int


@dataclass
class CompressionResult:
    status: str  # "normal" | "suspicious" | "insufficient_data"
    severity: str  # "low" | "medium" | "high"
    confidence: float
    scores: dict[str, Optional[float]] = field(default_factory=dict)
    description: str = ""


def _blockiness_score(gray_region: np.ndarray) -> Optional[float]:
    """
    Cheap blockiness proxy: ratio of mean gradient magnitude AT 8px block
    boundaries vs mean gradient magnitude WITHIN blocks. Higher = more
    visible blocking artifact (heavier / different JPEG compression history).
    """
    h, w = gray_region.shape[:2]
    if h < JPEG_BLOCK * 2 or w < JPEG_BLOCK * 2:
        return None

    region = gray_region.astype(np.float64)

    # Horizontal gradient (difference between adjacent columns)
    grad_x = np.abs(np.diff(region, axis=1))
    boundary_cols = np.arange(JPEG_BLOCK - 1, w - 1, JPEG_BLOCK)
    if boundary_cols.size == 0:
        return None
    boundary_mask = np.zeros(grad_x.shape[1], dtype=bool)
    boundary_mask[boundary_cols] = True

    boundary_energy = grad_x[:, boundary_mask].mean() if boundary_mask.any() else 0.0
    within_energy = grad_x[:, ~boundary_mask].mean() if (~boundary_mask).any() else 0.0

    if within_energy < 1e-6:
        return None

    return float(boundary_energy / within_energy)


def analyze_local_compression(
    image_np_bgr: np.ndarray,
    regions: dict[str, Optional[RegionBox]],
) -> CompressionResult:
    """
    Compare blockiness signatures across named regions (e.g. "photo", "mrz",
    "background"). Regions that are None/too small are skipped.
    """
    gray = cv2.cvtColor(image_np_bgr, cv2.COLOR_BGR2GRAY)

    scores: dict[str, Optional[float]] = {}
    for name, box in regions.items():
        if box is None:
            scores[name] = None
            continue
        crop = gray[box.y:box.y + box.height, box.x:box.x + box.width]
        scores[name] = _blockiness_score(crop)

    valid_scores = {k: v for k, v in scores.items() if v is not None}

    if len(valid_scores) < 2:
        return CompressionResult(
            status="insufficient_data",
            severity="low",
            confidence=0.0,
            scores=scores,
            description=(
                "Too few comparable regions were available to assess local "
                "compression consistency."
            ),
        )

    max_score = max(valid_scores.values())
    min_score = min(valid_scores.values())
    ratio = (max_score + 1e-6) / (min_score + 1e-6)

    if ratio >= INCONSISTENCY_RATIO_HIGH:
        status, severity = "suspicious", "high"
        description = (
            f"Large compression-signature difference (ratio={ratio:.2f}x) was found "
            "between document regions. This can indicate a spliced or re-saved region, "
            "but can also result from normal differences between photo, text, and "
            "background content."
        )
    elif ratio >= INCONSISTENCY_RATIO_SUSPICIOUS:
        status, severity = "suspicious", "medium"
        description = (
            f"A moderate compression-signature difference (ratio={ratio:.2f}x) was found "
            "between document regions. Different content types naturally compress "
            "differently, so this is a weak indicator on its own."
        )
    else:
        status, severity = "normal", "low"
        description = (
            "Compression characteristics are broadly consistent across the compared "
            "document regions."
        )

    confidence = round(min(0.85, 0.4 + 0.1 * len(valid_scores)), 2)

    logger.info(
        "Compression analysis: status=%s severity=%s ratio=%.2f regions_compared=%d",
        status, severity, ratio, len(valid_scores),
    )

    return CompressionResult(
        status=status,
        severity=severity,
        confidence=confidence,
        scores={k: (round(v, 3) if v is not None else None) for k, v in scores.items()},
        description=description,
    )
