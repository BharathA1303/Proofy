"""
backend/app/services/forensics/photo_boundary.py

Module 3: Photo Region Detection + Photo Boundary / Edge Analysis.

Module 1 (OCR) does not produce a passport photo bounding box, so this
module attempts its own dedicated, conservative detection strategy based
on the typical layout of a TD3 passport bio-data page (a rectangular
photograph in the upper portion of the document, portrait-oriented).

Two-tier detection strategy:
  Tier 1 — Dynamic Canny/contour geometry (unchanged from the original
           implementation). Works well on clean, high-contrast captures.
  Tier 2 — Profile fallback. When Tier 1 cannot reliably establish a
           rectangular candidate (low contrast, glare, a deliberately
           blurred/feathered edge intended to defeat contour detection),
           we do NOT exempt the document from boundary analysis. Instead
           we fall back to the document profile's declared
           `expected_regions["photo"]` coordinates (relative_x/y/w/h) and
           run the same boundary analysis against that fixed mask.

This closes a loophole where a forger who blurs or feathers the photo
edge specifically to defeat Tier 1 contour detection would previously
have been *exempted* from boundary analysis entirely (status="unavailable")
rather than flagged. Now the boundary is still checked, at the coordinates
the document is structurally expected to carry a photo — and the fact that
detection had to fall back at all is itself recorded as tracking evidence.

Boundary analysis (once a region is known, by either tier) looks for:
  - Edge-strength discontinuity along the photo border vs. its immediate
    surroundings
  - Local texture variance mismatch between the photo interior and the
    document background just outside the boundary

None of these signals alone imply photo replacement — a normal printed
photo also has a strong rectangular edge. We only report a "suspicious"
boundary when the discontinuity metrics diverge sharply from what a
uniformly printed/scanned photo would show. A fallback-tier detection
that ALSO shows high-variance boundary abnormalities is treated as a
stronger indicator (see PhotoBoundaryResult.evidence_item) precisely
because it combines two independent red flags: the edge could not be
confirmed geometrically, AND the profile-expected location shows an
artificial-looking transition.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from app.schemas.evidence import (
    EvidenceModule,
    EvidenceSeverity,
    EvidenceStatus,
    NormalizedEvidenceItem,
)
from app.services.documents.profiles.document_profile_registry import document_profile_registry

logger = logging.getLogger(__name__)

# ── Photo region detection thresholds (Tier 1: dynamic contour) ────────────
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

# ── Profile fallback (Tier 2) ───────────────────────────────────────────────
# Confidence assigned to a fallback-tier region: lower than a genuine geometric
# detection (which can reach up to MIN_RECTANGULARITY-bounded ~0.9), since we
# are trusting the document profile's declared layout rather than measuring it.
FALLBACK_CONFIDENCE = 0.55
# Minimum pixel span (in each dimension) for a fallback region to be usable.
FALLBACK_MIN_DIMENSION_PX = 20

# ── Boundary analysis thresholds ────────────────────────────────────────────
BOUNDARY_MARGIN = 6
EDGE_DENSITY_SUSPICIOUS = 0.55
TEXTURE_RATIO_SUSPICIOUS = 3.0
MIN_BACKGROUND_TEXTURE_VARIANCE = 5.0

# ── Fallback-tier variance-abnormality escalation (requirement #4) ─────────
# When detection had to fall back to profile coordinates AND the measured
# boundary shows high-variance abnormalities at or above these levels, we
# raise a CRITICAL-adjacent, high-severity NormalizedEvidenceItem — this
# combination (unverifiable edge geometry + abnormal texture transition at
# the expected photo location) is a stronger signal than either alone.
FALLBACK_HIGH_EDGE_DENSITY = 0.62
FALLBACK_HIGH_TEXTURE_RATIO = 4.5
FALLBACK_HIGH_RING_VARIANCE = 14000.0


@dataclass
class PhotoRegion:
    x: int
    y: int
    width: int
    height: int


@dataclass
class PhotoRegionResult:
    status: str  # "detected" | "fallback" | "unavailable"
    region: Optional[PhotoRegion]
    confidence: float
    method: str  # "contour_geometry" | "profile_fallback" | "none"


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
    detection_tier: str = "none"  # "contour_geometry" | "profile_fallback" | "none"
    evidence_item: Optional[NormalizedEvidenceItem] = None


def _resolve_profile_photo_region(
    image_np_bgr: np.ndarray,
    document_type: str,
) -> Optional[PhotoRegion]:
    """
    Look up the document profile's declared `expected_regions["photo"]`
    (relative_x/relative_y/relative_w/relative_h) and convert it to a pixel
    PhotoRegion for the given image. Returns None if the profile is unknown,
    has no declared photo region, or the resulting box is degenerate.

    Never raises — an unsupported/unknown document_type here must not break
    forensic analysis for that document, it just means no fallback mask is
    available and the caller stays "unavailable".
    """
    try:
        profile = document_profile_registry.resolve(document_type)
    except Exception as exc:
        logger.debug("Photo region fallback: could not resolve profile for '%s': %s", document_type, exc)
        return None

    expected = getattr(profile, "expected_regions", None) or {}
    photo_cfg = expected.get("photo")
    if not photo_cfg:
        logger.debug("Photo region fallback: profile '%s' has no expected 'photo' region.", document_type)
        return None

    try:
        rel_x = float(photo_cfg["relative_x"])
        rel_y = float(photo_cfg["relative_y"])
        rel_w = float(photo_cfg["relative_w"])
        rel_h = float(photo_cfg["relative_h"])
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Photo region fallback: malformed expected_regions['photo'] for '%s': %s", document_type, exc)
        return None

    h, w = image_np_bgr.shape[:2]
    px = int(round(rel_x * w))
    py = int(round(rel_y * h))
    pw = int(round(rel_w * w))
    ph = int(round(rel_h * h))

    # Clamp to image bounds defensively.
    px = max(0, min(px, w - 1))
    py = max(0, min(py, h - 1))
    pw = max(0, min(pw, w - px))
    ph = max(0, min(ph, h - py))

    if pw < FALLBACK_MIN_DIMENSION_PX or ph < FALLBACK_MIN_DIMENSION_PX:
        logger.warning(
            "Photo region fallback: resolved box too small (w=%d h=%d) for document_type='%s'.",
            pw, ph, document_type,
        )
        return None

    return PhotoRegion(x=px, y=py, width=pw, height=ph)


def detect_photo_region(
    image_np_bgr: np.ndarray,
    document_type: str = "passport",
) -> PhotoRegionResult:
    """
    Attempt to locate the passport photograph via contour geometry
    (Tier 1). If no candidate clears the rectangularity / geometry bar —
    e.g. low contrast, glare, or a deliberately blurred/feathered edge —
    fall back to the document profile's declared expected photo region
    (Tier 2) rather than exempting the document from boundary analysis.

    Returns PhotoRegionResult.status:
      "detected"    — Tier 1 geometric detection succeeded.
      "fallback"    — Tier 1 failed; Tier 2 profile coordinates were used.
      "unavailable" — Both tiers failed (no contour candidate AND no usable
                       profile-declared photo region for this document type).
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

    if best is not None:
        rectangularity, region = best
        confidence = round(min(0.9, rectangularity), 2)
        logger.info(
            "Photo region detected (contour_geometry): x=%d y=%d w=%d h=%d confidence=%.2f",
            region.x, region.y, region.width, region.height, confidence,
        )
        return PhotoRegionResult(
            status="detected", region=region, confidence=confidence, method="contour_geometry",
        )

    # ── Tier 1 failed: log a tracking state event and fall back to Tier 2 ──
    logger.info(
        "TRACKING_EVENT photo_region_detection_fallback: dynamic contour detection found no reliable "
        "candidate (document_type=%s, image=%dx%d). Falling back to document profile expected region "
        "instead of exempting this document from boundary analysis.",
        document_type, w, h,
    )

    fallback_region = _resolve_profile_photo_region(image_np_bgr, document_type)
    if fallback_region is not None:
        logger.info(
            "Photo region resolved via profile_fallback: x=%d y=%d w=%d h=%d document_type=%s",
            fallback_region.x, fallback_region.y, fallback_region.width, fallback_region.height, document_type,
        )
        return PhotoRegionResult(
            status="fallback",
            region=fallback_region,
            confidence=FALLBACK_CONFIDENCE,
            method="profile_fallback",
        )

    logger.info(
        "Photo region detection: no reliable candidate found and no usable profile fallback "
        "(document_type=%s).", document_type,
    )
    return PhotoRegionResult(status="unavailable", region=None, confidence=0.0, method="none")


def _local_texture_variance(gray: np.ndarray) -> float:
    """Variance of the Laplacian — a cheap local-texture / focus proxy."""
    if gray.size == 0:
        return 0.0
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def analyze_photo_boundary(
    image_np_bgr: np.ndarray,
    photo_region_result: PhotoRegionResult,
    document_type: str = "passport",
    document_id: Optional[str] = None,
) -> PhotoBoundaryResult:
    """
    Analyze the boundary of a photo region (from either detection tier) for
    suspicious discontinuities. Runs identically whether the region came
    from Tier 1 (contour geometry) or Tier 2 (profile fallback) — the two
    tiers only differ in how confident we are in the region's placement,
    not in how the boundary itself is measured.

    Returns status="unavailable" only when NO region is available at all
    (both detection tiers failed) — a document is never silently exempted
    from boundary analysis just because Tier 1 contour detection failed.
    """
    if photo_region_result.status == "unavailable" or photo_region_result.region is None:
        return PhotoBoundaryResult(
            status="unavailable",
            severity="low",
            confidence=0.0,
            indicators=[],
            description=(
                "No passport photo region could be identified by dynamic detection or by the "
                "document profile's expected layout, so boundary analysis was not performed."
            ),
            detection_tier="none",
        )

    is_fallback_tier = photo_region_result.status == "fallback"
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
            detection_tier=photo_region_result.method,
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

    ring_lap = cv2.Laplacian(outer, cv2.CV_64F)[ring_mask]
    ring_variance = float(ring_lap.var()) if ring_lap.size else 0.0
    inner_variance = float(cv2.Laplacian(inner, cv2.CV_64F).var()) if inner.size else 0.0

    if min(inner_variance, ring_variance) >= 50.0:
        texture_ratio = (max(inner_variance, ring_variance) + 1e-6) / (min(inner_variance, ring_variance) + 1e-6)
    else:
        texture_ratio = 1.0

    indicators: list[BoundaryIndicator] = []

    if edge_density >= EDGE_DENSITY_SUSPICIOUS:
        indicators.append(BoundaryIndicator(
            type="edge_discontinuity", severity="medium", region=region,
        ))

    # Texture discontinuity: only meaningful when both regions contain texture, or if ring has severe alteration noise
    if ring_variance >= 10000.0 or texture_ratio >= TEXTURE_RATIO_SUSPICIOUS:
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

    if is_fallback_tier:
        description = (
            "Dynamic photo-region detection could not confirm a geometric boundary "
            "(possible low contrast, glare, or a deliberately obscured edge); analysis "
            "fell back to the document profile's expected photo location. " + description
        )

    confidence = round(min(0.9, photo_region_result.confidence + 0.05), 2)

    logger.info(
        "Photo boundary analysis: status=%s severity=%s tier=%s edge_density=%.3f texture_ratio=%.2f "
        "ring_variance=%.1f",
        status, severity, photo_region_result.method, edge_density, texture_ratio, ring_variance,
    )

    # ── Requirement #4: fallback-tier + high-variance abnormality escalation ──
    # Dynamic detection failing is not, by itself, suspicious (many genuine
    # captures have low contrast or glare). But dynamic detection failing
    # AND the profile-expected location showing high-variance boundary
    # abnormalities is a materially stronger combined signal — a forger who
    # blurred/feathered the photo edge to defeat Tier 1 would produce exactly
    # this pattern. That combination is escalated into a dedicated
    # high-severity NormalizedEvidenceItem, on top of the ordinary
    # status/severity fields above.
    evidence_item: Optional[NormalizedEvidenceItem] = None
    if is_fallback_tier:
        high_variance_abnormality = (
            edge_density >= FALLBACK_HIGH_EDGE_DENSITY
            or texture_ratio >= FALLBACK_HIGH_TEXTURE_RATIO
            or ring_variance >= FALLBACK_HIGH_RING_VARIANCE
        )
        if high_variance_abnormality:
            evidence_item = NormalizedEvidenceItem(
                document_id=document_id or "unknown",
                document_type=document_type,
                module=EvidenceModule.FORENSICS,
                signal_type="photo_boundary_fallback_variance_anomaly",
                status=EvidenceStatus.SUSPICIOUS,
                severity=EvidenceSeverity.HIGH,
                confidence=confidence,
                description=(
                    "Dynamic photo-boundary detection failed to establish a geometric edge "
                    "(low contrast, glare, or a deliberately obscured boundary), and the "
                    "document profile's expected photo location shows high-variance boundary "
                    f"abnormalities (edge_density={edge_density:.3f}, texture_ratio={texture_ratio:.2f}, "
                    f"ring_variance={ring_variance:.1f}). This combination — an unverifiable edge "
                    "geometry paired with an abnormal texture transition at the structurally expected "
                    "photo location — is a stronger indicator than either signal alone."
                ),
                source="forensics.photo_boundary.fallback_tier",
                module_version="1.1.0",
                provenance={
                    "detection_tier": photo_region_result.method,
                    "region": {"x": region.x, "y": region.y, "width": region.width, "height": region.height},
                    "edge_density": round(edge_density, 4),
                    "texture_ratio": round(texture_ratio, 3),
                    "ring_variance": round(ring_variance, 2),
                    "inner_variance": round(inner_variance, 2),
                },
            )
            logger.warning(
                "TRACKING_EVENT photo_boundary_fallback_high_variance: document_type=%s document_id=%s "
                "edge_density=%.3f texture_ratio=%.2f ring_variance=%.1f",
                document_type, document_id or "unknown", edge_density, texture_ratio, ring_variance,
            )
            # A confirmed fallback-tier variance anomaly is always reported as at
            # least "suspicious"/"high" to the caller, even if only one ordinary
            # indicator fired above (which alone would have been "medium").
            status, severity = "suspicious", "high"

    return PhotoBoundaryResult(
        status=status,
        severity=severity,
        confidence=confidence,
        indicators=indicators,
        description=description,
        detection_tier=photo_region_result.method,
        evidence_item=evidence_item,
    )
