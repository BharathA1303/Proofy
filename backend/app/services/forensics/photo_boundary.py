"""
backend/app/services/forensics/photo_boundary.py

Module 3: Photo Region Detection + Photo Boundary / Edge Analysis.

Module 1 (OCR) does not produce a passport photo bounding box, so this
module attempts its own dedicated, conservative detection strategy based
on the typical layout of a TD3 passport bio-data page (a rectangular
photograph in the upper portion of the document, portrait-oriented).

If no candidate rectangle meets the confidence bar, we report
status="unavailable" rather than fabricate coordinates.

Boundary analysis (once a region is known) looks for:
  - Edge-strength discontinuity along the photo border vs. its immediate
    surroundings
  - Local texture variance mismatch between the photo interior and the
    document background just outside the boundary

None of these signals alone imply photo replacement — a normal printed
photo also has a strong rectangular edge. We only report a "suspicious"
boundary when the discontinuity metrics diverge sharply from what a
uniformly printed/scanned photo would show.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ── Photo region detection thresholds ──────────────────────────────────────
# Passport photos are portrait-oriented and occupy a modest fraction of the page.
MIN_AREA_RATIO = 0.02
MAX_AREA_RATIO = 0.22
MIN_ASPECT = 0.55   # width / height
MAX_ASPECT = 1.05
# Must be within the left ~65% of the page and the top ~75% (typical TD3 layout).
MAX_X_FRACTION = 0.65
MAX_Y_FRACTION = 0.75
# How close the contour's area must be to its bounding rect's area to be
# considered "rectangular" (a genuine photo edge, not a stray shape).
MIN_RECTANGULARITY = 0.85

# ── Boundary analysis thresholds ────────────────────────────────────────────
BOUNDARY_MARGIN = 6
EDGE_DENSITY_SUSPICIOUS = 0.55
TEXTURE_RATIO_SUSPICIOUS = 3.0


@dataclass
class PhotoRegion:
    x: int
    y: int
    width: int
    height: int


@dataclass
class PhotoRegionResult:
    status: str  # "detected" | "unavailable"
    region: Optional[PhotoRegion]
    confidence: float
    method: str


@dataclass
class BoundaryIndicator:
    type: str
    severity: str
    region: Optional[PhotoRegion] = None


@dataclass
class PhotoBoundaryResult:
    status: str  # "normal" | "suspicious" | "unavailable"
    severity: str  # "low" | "medium" | "high"
    confidence: float
    indicators: list[BoundaryIndicator] = field(default_factory=list)
    description: str = ""


def detect_photo_region(image_np_bgr: np.ndarray) -> PhotoRegionResult:
    """
    Attempt to locate the passport photograph via contour geometry.

    Conservative by design: returns "unavailable" rather than a low-confidence
    guess if no candidate clears the rectangularity / geometry bar.
    """
    h, w = image_np_bgr.shape[:2]
    image_area = h * w

    gray = cv2.cvtColor(image_np_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    best: Optional[tuple[float, PhotoRegion]] = None

    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)
        if cw == 0 or ch == 0:
            continue

        area_ratio = (cw * ch) / image_area
        if not (MIN_AREA_RATIO <= area_ratio <= MAX_AREA_RATIO):
            continue

        aspect = cw / ch
        if not (MIN_ASPECT <= aspect <= MAX_ASPECT):
            continue

        if (x + cw) > w * MAX_X_FRACTION or y > h * MAX_Y_FRACTION:
            continue

        contour_area = cv2.contourArea(contour)
        rectangularity = contour_area / (cw * ch)
        if rectangularity < MIN_RECTANGULARITY:
            continue

        # Score candidates by rectangularity — the most "photo-like" rectangle wins.
        if best is None or rectangularity > best[0]:
            best = (rectangularity, PhotoRegion(x=x, y=y, width=cw, height=ch))

    if best is None:
        logger.info("Photo region detection: no reliable candidate found.")
        return PhotoRegionResult(status="unavailable", region=None, confidence=0.0, method="contour_geometry")

    rectangularity, region = best
    confidence = round(min(0.9, rectangularity), 2)
    logger.info(
        "Photo region detected: x=%d y=%d w=%d h=%d confidence=%.2f",
        region.x, region.y, region.width, region.height, confidence,
    )
    return PhotoRegionResult(status="detected", region=region, confidence=confidence, method="contour_geometry")


def _local_texture_variance(gray: np.ndarray) -> float:
    """Variance of the Laplacian — a cheap local-texture / focus proxy."""
    if gray.size == 0:
        return 0.0
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def analyze_photo_boundary(
    image_np_bgr: np.ndarray,
    photo_region_result: PhotoRegionResult,
) -> PhotoBoundaryResult:
    """
    Analyze the boundary of a detected photo region for suspicious
    discontinuities. Requires a detected photo region; otherwise "unavailable".
    """
    if photo_region_result.status != "detected" or photo_region_result.region is None:
        return PhotoBoundaryResult(
            status="unavailable",
            severity="low",
            confidence=0.0,
            indicators=[],
            description=(
                "No passport photo region could be reliably identified, so boundary "
                "analysis was not performed."
            ),
        )

    region = photo_region_result.region
    h, w = image_np_bgr.shape[:2]
    gray = cv2.cvtColor(image_np_bgr, cv2.COLOR_BGR2GRAY)

    m = BOUNDARY_MARGIN
    x0, y0 = max(region.x - m, 0), max(region.y - m, 0)
    x1, y1 = min(region.x + region.width + m, w), min(region.y + region.height + m, h)

    outer = gray[y0:y1, x0:x1]
    inner = gray[region.y:region.y + region.height, region.x:region.x + region.width]

    if outer.size == 0 or inner.size == 0:
        return PhotoBoundaryResult(
            status="unavailable", severity="low", confidence=0.0,
            description="Photo region coordinates fell outside the image bounds.",
        )

    # Restrict measurement to the boundary RING itself (outer crop minus the
    # inner footprint) — the interior of a large photo would otherwise dilute
    # both metrics and hide a genuine border discontinuity.
    ring_mask = np.ones(outer.shape, dtype=bool)
    inner_y0, inner_x0 = region.y - y0, region.x - x0
    inner_y1, inner_x1 = inner_y0 + region.height, inner_x0 + region.width
    ring_mask[max(inner_y0, 0):inner_y1, max(inner_x0, 0):inner_x1] = False

    edges_outer = cv2.Canny(outer, 40, 120)
    ring_edge_pixels = edges_outer[ring_mask]
    edge_density = float((ring_edge_pixels > 0).mean()) if ring_edge_pixels.size else 0.0

    ring_pixels = outer[ring_mask]
    ring_variance = float(ring_pixels.astype(np.float64).var()) if ring_pixels.size else 0.0
    inner_variance = _local_texture_variance(inner)
    texture_ratio = (max(inner_variance, ring_variance) + 1e-6) / (min(inner_variance, ring_variance) + 1e-6)

    indicators: list[BoundaryIndicator] = []

    if edge_density >= EDGE_DENSITY_SUSPICIOUS:
        indicators.append(BoundaryIndicator(
            type="edge_discontinuity", severity="medium", region=region,
        ))

    if texture_ratio >= TEXTURE_RATIO_SUSPICIOUS:
        indicators.append(BoundaryIndicator(
            type="texture_discontinuity", severity="medium", region=region,
        ))

    if not indicators:
        status, severity = "normal", "low"
        description = (
            "Photo boundary edge strength and local texture are consistent with a "
            "normally printed or scanned photograph."
        )
    elif len(indicators) == 1:
        status, severity = "suspicious", "medium"
        description = (
            "The passport photo boundary shows a localized discontinuity "
            f"({indicators[0].type.replace('_', ' ')}) relative to the surrounding "
            "document background. This can occur naturally from lamination glare, "
            "scan artifacts, or printing — further review is recommended."
        )
    else:
        status, severity = "suspicious", "high"
        description = (
            "Multiple independent boundary indicators (edge and texture discontinuity) "
            "were found around the passport photo region. Further review is recommended."
        )

    confidence = round(min(0.9, photo_region_result.confidence + 0.05), 2)

    logger.info(
        "Photo boundary analysis: status=%s severity=%s edge_density=%.3f texture_ratio=%.2f",
        status, severity, edge_density, texture_ratio,
    )

    return PhotoBoundaryResult(
        status=status,
        severity=severity,
        confidence=confidence,
        indicators=indicators,
        description=description,
    )
