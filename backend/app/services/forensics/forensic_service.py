"""
backend/app/services/forensics/forensic_service.py

Module 3: Tampering & Forensic Analysis — orchestrator.

Pipeline:

    Original Passport Image
              |
              v
      Image Quality Check ---> insufficient? --> return "insufficient_data"
              |
      +-------+--------+---------+
      |                |         |
      v                v         v
     ELA        Photo Boundary  Metadata
      |                |         |
      +-------+--------+---------+
              |
     Local Compression (uses photo region + MRZ-band heuristic)
              |
              v
      Forensic Evidence (signals)
              |
              v
      Conservative Aggregation -> overall_assessment

Each technique is implemented in its own module and is independently
testable. This module only wires them together and builds the response
schema — it intentionally contains no forensic logic of its own.
"""
from __future__ import annotations

import logging

import numpy as np

from app.schemas.forensics import ForensicAnalysisSummary, ForensicSignal, PhotoRegionBox
from app.services.forensics.aggregator import SignalVote, aggregate_forensic_signals
from app.services.forensics.compression_analysis import RegionBox, analyze_local_compression
from app.services.forensics.ela import run_ela
from app.services.forensics.image_quality import assess_image_quality
from app.services.forensics.metadata_analysis import analyze_metadata
from app.services.forensics.photo_boundary import analyze_photo_boundary, detect_photo_region
from app.services.forensics.stamp_analysis import analyze_document_stamps

logger = logging.getLogger(__name__)

# MRZ occupies roughly the bottom band of a TD3 passport bio-data page.
# This mirrors the same conservative assumption Module 1's MRZ-zone search uses.
_MRZ_BAND_TOP_FRACTION = 0.82
_MRZ_BAND_BOTTOM_FRACTION = 0.98
_MRZ_BAND_SIDE_MARGIN_FRACTION = 0.05

# A background/security-pattern sampling block: upper-right quadrant strip,
# chosen to avoid the typical photo (upper-left) and MRZ (bottom) zones.
_BG_X_FRACTION = (0.68, 0.94)
_BG_Y_FRACTION = (0.06, 0.22)


def _mrz_band(h: int, w: int) -> RegionBox:
    x0 = int(w * _MRZ_BAND_SIDE_MARGIN_FRACTION)
    x1 = int(w * (1 - _MRZ_BAND_SIDE_MARGIN_FRACTION))
    y0 = int(h * _MRZ_BAND_TOP_FRACTION)
    y1 = int(h * _MRZ_BAND_BOTTOM_FRACTION)
    return RegionBox(x=x0, y=y0, width=max(x1 - x0, 1), height=max(y1 - y0, 1))


def _background_block(h: int, w: int) -> RegionBox:
    x0, x1 = int(w * _BG_X_FRACTION[0]), int(w * _BG_X_FRACTION[1])
    y0, y1 = int(h * _BG_Y_FRACTION[0]), int(h * _BG_Y_FRACTION[1])
    return RegionBox(x=x0, y=y0, width=max(x1 - x0, 1), height=max(y1 - y0, 1))


def run_forensic_analysis(
    raw_bytes: bytes,
    image_np_bgr: np.ndarray,
    document_type: str = "passport",
) -> ForensicAnalysisSummary:
    """
    Execute Module 3 forensic analysis on the original uploaded image.

    Args:
        raw_bytes:     Original file bytes (used for metadata analysis only —
                        never logged, never persisted).
        image_np_bgr:  Decoded original image (BGR), NOT the OCR-preprocessed
                        image — Module 3 must operate on the original upload.
        document_type: Canonical document type string ('passport', 'visa', etc.)
                        Configures regional sampling for compression analysis.
    """
    h, w = image_np_bgr.shape[:2]

    quality = assess_image_quality(image_np_bgr)
    if quality.status == "insufficient":
        logger.info("Forensic analysis skipped: image quality insufficient.")
        return ForensicAnalysisSummary(
            status="insufficient_data",
            overall_assessment="insufficient_data",
            explanation=(
                "Image quality is insufficient for reliable forensic analysis. "
                + " ".join(quality.reasons)
            ),
            signals=[],
            photo_region=None,
            quality_reasons=quality.reasons,
        )

    # ── ELA ──────────────────────────────────────────────────────────────
    ela_result = run_ela(image_np_bgr)
    ela_signal = ForensicSignal(
        type="ela",
        status=ela_result.status,
        severity=ela_result.severity,
        confidence=ela_result.confidence,
        description=ela_result.description,
        region=(
            PhotoRegionBox(
                x=ela_result.regions[0].x, y=ela_result.regions[0].y,
                width=ela_result.regions[0].width, height=ela_result.regions[0].height,
            ) if ela_result.regions else None
        ),
        metrics={
            "mean_error": ela_result.mean_error,
            "max_error": ela_result.max_error,
            "std_error": ela_result.std_error,
            "flagged_area_ratio": ela_result.flagged_area_ratio,
            "flagged_region_count": len(ela_result.regions),
        },
    )

    # ── Photo region + boundary ──────────────────────────────────────────
    photo_region_result = detect_photo_region(image_np_bgr)
    boundary_result = analyze_photo_boundary(image_np_bgr, photo_region_result)

    photo_region_schema = (
        PhotoRegionBox(
            x=photo_region_result.region.x, y=photo_region_result.region.y,
            width=photo_region_result.region.width, height=photo_region_result.region.height,
        ) if photo_region_result.status == "detected" and photo_region_result.region else None
    )

    boundary_signal = ForensicSignal(
        type="photo_boundary",
        status=boundary_result.status,
        severity=boundary_result.severity,
        confidence=boundary_result.confidence,
        description=boundary_result.description,
        region=photo_region_schema,
        metrics={"indicator_count": len(boundary_result.indicators)},
    )

    # ── Local compression consistency ────────────────────────────────────
    photo_box = (
        RegionBox(
            x=photo_region_result.region.x, y=photo_region_result.region.y,
            width=photo_region_result.region.width, height=photo_region_result.region.height,
        ) if photo_region_result.status == "detected" and photo_region_result.region else None
    )

    # Configure regions dynamically based on document profile
    norm_type = document_type.lower() if document_type else "passport"
    if norm_type == "passport":
        compression_regions = {
            "photo": photo_box,
            "mrz": _mrz_band(h, w),
            "background": _background_block(h, w),
        }
    else:
        # For non-passport documents (e.g. Visa), do not assume an MRZ band
        text_w = max(1, int(w * 0.45))
        text_h = max(1, int(h * 0.40))
        text_x = min(w - text_w, int(w * 0.45))
        text_y = min(h - text_h, int(h * 0.20))
        compression_regions = {
            "photo": photo_box,
            "text": RegionBox(x=text_x, y=text_y, width=text_w, height=text_h),
            "background": _background_block(h, w),
        }

    compression_result = analyze_local_compression(
        image_np_bgr,
        regions=compression_regions,
    )
    compression_signal = ForensicSignal(
        type="compression",
        status=compression_result.status,
        severity=compression_result.severity,
        confidence=compression_result.confidence,
        description=compression_result.description,
        region=None,
        metrics={k: v for k, v in compression_result.scores.items() if v is not None},
    )

    # ── Metadata ──────────────────────────────────────────────────────────
    metadata_result = analyze_metadata(raw_bytes)
    metadata_signal = ForensicSignal(
        type="metadata",
        status=metadata_result.status,
        severity=metadata_result.severity,
        confidence=metadata_result.confidence,
        description=metadata_result.description,
        region=None,
        metrics={"field_count": len(metadata_result.fields_present)},
    )

    # ── Stamp & Consular Seal Analysis ────────────────────────────────────
    stamp_result = analyze_document_stamps(image_np_bgr, document_type=document_type)
    stamp_region = (
        PhotoRegionBox(
            x=stamp_result.indicators[0].region_box["x"],
            y=stamp_result.indicators[0].region_box["y"],
            width=stamp_result.indicators[0].region_box["width"],
            height=stamp_result.indicators[0].region_box["height"],
        )
        if stamp_result.indicators and stamp_result.indicators[0].region_box
        else None
    )
    stamp_signal = ForensicSignal(
        type="stamp",
        status=stamp_result.status,
        severity=stamp_result.severity,
        confidence=stamp_result.confidence,
        description=stamp_result.description,
        region=stamp_region,
        metrics=stamp_result.metrics,
    )

    signals = [ela_signal, boundary_signal, compression_signal, metadata_signal, stamp_signal]

    # ── Aggregation ───────────────────────────────────────────────────────
    # Only signals that actually produced a measurement vote; "unavailable",
    # "insufficient_data", and "not_applicable" signals are excluded from the vote.
    votes = [
        SignalVote(type=s.type, status=s.status, severity=s.severity)
        for s in signals
        if s.status not in ("unavailable", "insufficient_data", "not_applicable")
    ]
    # Metadata can never contribute a "strong" vote on its own — cap it.
    for v in votes:
        if v.type == "metadata" and v.severity == "high":
            v.severity = "medium"

    overall_assessment, explanation = aggregate_forensic_signals(votes)

    logger.info(
        "Forensic analysis complete: overall=%s signals=%d",
        overall_assessment, len(signals),
    )

    return ForensicAnalysisSummary(
        status="completed",
        overall_assessment=overall_assessment,
        explanation=explanation,
        signals=signals,
        photo_region=photo_region_schema,
        quality_reasons=[],
    )
