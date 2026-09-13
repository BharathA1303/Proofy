"""
backend/app/services/document_forensics/service.py

Unified Production-Grade Document Forensics & Tampering Analysis Service (M3).
Coordinates optical quality gates, classical forensic detectors (ELA, JPEG compression,
copy-move duplication, edge splicing), deep-learning model telemetry, spatial localization,
and multi-signal evidence aggregation.
"""
from __future__ import annotations

import hashlib
import io
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image

from app.services.document_intelligence.schema import NormalizedBBox
from app.services.document_forensics.classical import ClassicalForensicEngine
from app.services.document_forensics.localization import ForensicLocalizationEngine
from app.services.document_forensics.quality import DocumentQualityEngine
from app.services.document_forensics.schema import (
    AIModelForensicResult,
    DocumentBoundaryResult,
    ForensicAnomalyState,
    ForensicFinding,
    ForensicResult,
    ForensicStatus,
    ImageQualityAssessment,
    ModelStatus,
    SignalSeverity,
    SignalStatus,
    SignalType,
    SuspiciousRegion,
)
from app.services.document_forensics.tampering_model import DocumentTamperingModel
from app.services.documents.profiles.document_profile_registry import document_profile_registry

logger = logging.getLogger(__name__)

# Security constraints
MAX_IMAGE_DIMENSION_PX = 10000  # 10,000 x 10,000 = 100 MP limit
MAX_RAW_BYTES_SIZE = 25 * 1024 * 1024  # 25 MB max
ENGINE_VERSION = "8.0.0"


def _to_cv2_image_and_bytes(
    image_input: Union[np.ndarray, Image.Image, bytes, str, Path],
    raw_bytes: Optional[bytes] = None,
) -> Tuple[np.ndarray, bytes, str]:
    """
    Standardize input into BGR numpy array, raw bytes, and SHA-256 digest.
    Applies security bounds against decompression bombs.
    """
    if isinstance(image_input, bytes):
        if len(image_input) > MAX_RAW_BYTES_SIZE:
            raise ValueError(f"Image payload exceeds maximum allowed size ({len(image_input)} > {MAX_RAW_BYTES_SIZE} bytes)")
        img_bytes = image_input
        sha256_hash = hashlib.sha256(img_bytes).hexdigest()
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Failed to decode image bytes into valid image.")
        return img, img_bytes, sha256_hash

    if isinstance(image_input, (str, Path)):
        p = Path(image_input)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {image_input}")
        img_bytes = p.read_bytes()
        sha256_hash = hashlib.sha256(img_bytes).hexdigest()
        img = cv2.imread(str(p))
        if img is None:
            raise ValueError(f"OpenCV could not read image at path: {image_input}")
        return img, img_bytes, sha256_hash

    if isinstance(image_input, Image.Image):
        # Prevent decompression bombs
        if image_input.width > MAX_IMAGE_DIMENSION_PX or image_input.height > MAX_IMAGE_DIMENSION_PX:
            raise ValueError(f"Image dimensions exceed maximum allowed ({image_input.size} > {MAX_IMAGE_DIMENSION_PX}px)")
        rgb = np.array(image_input.convert("RGB"))
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        if raw_bytes is None:
            buf = io.BytesIO()
            image_input.save(buf, format="JPEG", quality=95)
            img_bytes = buf.getvalue()
        else:
            img_bytes = raw_bytes
        sha256_hash = hashlib.sha256(img_bytes).hexdigest()
        return bgr, img_bytes, sha256_hash

    if isinstance(image_input, np.ndarray):
        img = image_input
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        elif img.ndim == 3 and img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)

        h, w = img.shape[:2]
        if h > MAX_IMAGE_DIMENSION_PX or w > MAX_IMAGE_DIMENSION_PX:
            raise ValueError(f"Array dimensions exceed maximum allowed ({w}x{h} > {MAX_IMAGE_DIMENSION_PX}px)")

        if raw_bytes is None:
            _, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
            img_bytes = enc.tobytes()
        else:
            img_bytes = raw_bytes
        sha256_hash = hashlib.sha256(img_bytes).hexdigest()
        return img, img_bytes, sha256_hash

    raise TypeError(f"Unsupported image input type: {type(image_input)}")


class DocumentForensicsService:
    """
    Production-grade document-agnostic tampering & forensic authenticity service.
    Follows strict evidence architecture: answers whether forensic evidence
    suggests digital manipulation, but NEVER emits FORGED_DOCUMENT.
    """

    def __init__(
        self,
        quality_engine: Optional[DocumentQualityEngine] = None,
        classical_engine: Optional[ClassicalForensicEngine] = None,
        tampering_model: Optional[DocumentTamperingModel] = None,
        localization_engine: Optional[ForensicLocalizationEngine] = None,
    ) -> None:
        self.quality_engine = quality_engine or DocumentQualityEngine()
        self.classical_engine = classical_engine or ClassicalForensicEngine()
        self.tampering_model = tampering_model or DocumentTamperingModel()
        self.localization_engine = localization_engine or ForensicLocalizationEngine()

    def analyze(
        self,
        image_input: Union[np.ndarray, Image.Image, bytes, str, Path],
        document_type: str = "driving_license",
        raw_bytes: Optional[bytes] = None,
        semantic_regions: Optional[Dict[str, NormalizedBBox]] = None,
        profile_override: Optional[Dict[str, Any]] = None,
    ) -> ForensicResult:
        """
        Execute full M3 forensic tampering evaluation.

        Args:
            image_input: Input document image in any format.
            document_type: Target credential type.
            raw_bytes: Original file bytes (for metadata analysis).
            semantic_regions: Semantic region boxes from M1 Document Intelligence.
            profile_override: Optional profile config overrides for tests.

        Returns:
            ForensicResult structured evidence object.
        """
        start_time = time.perf_counter()
        telemetry: Dict[str, Any] = {
            "document_type": document_type,
            "engine_version": ENGINE_VERSION,
        }

        # 1. Resolve Document Profile Configuration
        profile_config, profile_version = self._resolve_profile(document_type, profile_override)
        applicable = profile_config.get("applicable", True)

        if not applicable:
            telemetry["duration_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
            return ForensicResult(
                document_type=document_type,
                status=ForensicStatus.FORENSIC_UNAVAILABLE,
                anomaly_state=ForensicAnomalyState.INCONCLUSIVE,
                overall_explanation="Document forensics is declared not applicable for this credential type in profile.",
                findings=[],
                suspicious_regions=[],
                quality=ImageQualityAssessment(
                    is_adequate=True, status="adequate", width=0, height=0,
                    aspect_ratio=0.0, blur_score=0.0, brightness_mean=0.0,
                    contrast_std=0.0, noise_score=0.0,
                ),
                profile_version=profile_version,
                forensic_engine_version=ENGINE_VERSION,
                telemetry=telemetry,
            )

        # 2. Ingest and Hash Image
        try:
            img_bgr, img_bytes, sha256_hash = _to_cv2_image_and_bytes(image_input, raw_bytes)
        except Exception as exc:
            logger.warning("DocumentForensicsService: image ingestion error: %s", exc)
            telemetry["duration_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
            return ForensicResult(
                document_type=document_type,
                status=ForensicStatus.FORENSIC_UNAVAILABLE,
                anomaly_state=ForensicAnomalyState.INCONCLUSIVE,
                overall_explanation=f"Image input could not be processed safely: {exc}",
                findings=[],
                suspicious_regions=[],
                quality=ImageQualityAssessment(
                    is_adequate=False, status="insufficient", width=0, height=0,
                    aspect_ratio=0.0, blur_score=0.0, brightness_mean=0.0,
                    contrast_std=0.0, noise_score=0.0, reasons=[str(exc)],
                ),
                profile_version=profile_version,
                forensic_engine_version=ENGINE_VERSION,
                telemetry=telemetry,
            )

        telemetry["image_width"] = img_bgr.shape[1]
        telemetry["image_height"] = img_bgr.shape[0]

        # Merge semantic regions with profile-declared expected regions
        combined_regions: Dict[str, NormalizedBBox] = {}
        profile_regions = profile_config.get("regions", {})
        for r_name, r_cfg in profile_regions.items():
            if isinstance(r_cfg, dict) and "relative_box" in r_cfg:
                combined_regions[r_name] = r_cfg["relative_box"]
        if semantic_regions:
            combined_regions.update(semantic_regions)

        # 3. Quality Gate
        if "min_dimension" in profile_config:
            self.quality_engine.min_dimension = profile_config["min_dimension"]
        quality = self.quality_engine.assess(img_bgr)
        quality_finding = self.quality_engine.to_finding(quality)
        quality_finding.profile_version = profile_version
        findings: List[ForensicFinding] = [quality_finding]

        if not quality.is_adequate:
            # STOP downstream analysis on insufficient quality! Enforces FALSE POSITIVE CONTROL.
            telemetry["quality_status"] = "insufficient"
            telemetry["duration_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
            return ForensicResult(
                document_type=document_type,
                status=ForensicStatus.FORENSIC_INCONCLUSIVE,
                anomaly_state=ForensicAnomalyState.INCONCLUSIVE,
                overall_explanation=(
                    "Image quality is insufficient for conclusive forensic evaluation (optical defect / blur / low resolution). "
                    "This is an image quality limitation, not a finding of forgery."
                ),
                findings=findings,
                suspicious_regions=[],
                quality=quality,
                image_sha256=sha256_hash,
                profile_version=profile_version,
                forensic_engine_version=ENGINE_VERSION,
                telemetry=telemetry,
            )

        # 4. Classical Forensic Signals
        # 4A. ELA
        ela_finding, ela_blocks, ela_map = self.classical_engine.run_ela(img_bgr)
        findings.append(ela_finding)

        # 4B. JPEG Compression Consistency
        comp_finding = self.classical_engine.analyze_compression(img_bgr, combined_regions)
        findings.append(comp_finding)

        # 4C. Copy-Move Duplication
        copymove_finding = self.classical_engine.detect_copy_move(img_bgr)
        findings.append(copymove_finding)

        # 4D. Edge Splicing
        portrait_box = combined_regions.get("portrait_area") or combined_regions.get("photo")
        splicing_finding = self.classical_engine.analyze_splicing_edges(img_bgr, portrait_box)
        findings.append(splicing_finding)

        # 4E. Document Boundary
        boundary_res = self.classical_engine.detect_document_boundary(img_bgr)
        boundary_finding = ForensicFinding(
            finding_id="boundary_01",
            signal_type=SignalType.DOCUMENT_BOUNDARY,
            status=boundary_res.status,
            severity=SignalSeverity.MEDIUM if boundary_res.status == SignalStatus.BOUNDARY_SUSPICIOUS else SignalSeverity.LOW,
            confidence=0.85,
            bbox=boundary_res.contour_points,
            normalized_bbox=boundary_res.normalized_bbox,
            source="boundary_detector",
            explanation=boundary_res.details,
            metrics={"rectangularity": boundary_res.rectangularity_score, "aspect_ratio": boundary_res.aspect_ratio},
        )
        findings.append(boundary_finding)

        # 4F. EXIF / Metadata
        meta_finding = self.classical_engine.analyze_metadata(img_bytes)
        findings.append(meta_finding)

        # 5. Deep Learning Model Telemetry
        model_results: List[AIModelForensicResult] = []
        ai_res, ai_finding = self.tampering_model.predict(img_bgr)
        model_results.append(ai_res)
        if ai_finding:
            findings.append(ai_finding)

        # 6. Spatial Localization & Heatmap
        heatmap, suspicious_regions, regional_findings = self.localization_engine.generate_heatmap_and_regions(
            img_bgr, ela_map, combined_regions
        )
        findings.extend(regional_findings)

        # Attach profile version to all findings
        for f in findings:
            f.profile_version = profile_version

        # 7. Multi-Signal Evidence Aggregation
        status, anomaly_state, explanation = self._aggregate_evidence(findings, quality, model_results)

        telemetry["duration_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
        telemetry["findings_count"] = len(findings)
        telemetry["suspicious_regions_count"] = len(suspicious_regions)

        return ForensicResult(
            document_type=document_type,
            status=status,
            anomaly_state=anomaly_state,
            overall_explanation=explanation,
            findings=findings,
            suspicious_regions=suspicious_regions,
            quality=quality,
            boundary=boundary_res,
            metadata_details=meta_finding.metrics,
            model_results=model_results,
            image_sha256=sha256_hash,
            heatmap_grid=heatmap,
            profile_version=profile_version,
            forensic_engine_version=ENGINE_VERSION,
            telemetry=telemetry,
        )

    def _aggregate_evidence(
        self,
        findings: List[ForensicFinding],
        quality: ImageQualityAssessment,
        model_results: List[AIModelForensicResult],
    ) -> Tuple[ForensicStatus, ForensicAnomalyState, str]:
        """
        Deterministic, conservative multi-signal aggregation.
        Guarantees: A single weak anomaly alone NEVER flags FORENSIC_SUSPICIOUS.
        """
        # Active suspicious votes
        suspicious_findings = [
            f for f in findings
            if "suspicious" in f.status.value.lower() or "anomalous" in f.status.value.lower()
        ]
        strong_votes = [f for f in suspicious_findings if f.severity in (SignalSeverity.HIGH, SignalSeverity.CRITICAL)]
        weak_votes = [f for f in suspicious_findings if f.severity == SignalSeverity.MEDIUM]

        # AI Model impact
        model_flagged = any(
            m.status == ModelStatus.MODEL_AVAILABLE and m.tampering_detected is True for m in model_results
        )

        if model_flagged and (strong_votes or weak_votes):
            types = ", ".join(set(f.signal_type.value for f in suspicious_findings))
            return (
                ForensicStatus.FORENSIC_SUSPICIOUS,
                ForensicAnomalyState.MODEL_SUPPORTED_ANOMALY,
                f"Multiple independent forensic signals ({types}) and AI tampering inference identified suspicious anomalies.",
            )

        if len(strong_votes) >= 2:
            types = ", ".join(f.signal_type.value for f in strong_votes)
            return (
                ForensicStatus.FORENSIC_SUSPICIOUS,
                ForensicAnomalyState.MULTI_SIGNAL_ANOMALY,
                f"Multiple independent forensic indicators ({types}) identified strong anomalies.",
            )

        if len(strong_votes) == 1 and len(weak_votes) >= 1:
            types = ", ".join(f.signal_type.value for f in suspicious_findings)
            return (
                ForensicStatus.FORENSIC_SUSPICIOUS,
                ForensicAnomalyState.MULTI_SIGNAL_ANOMALY,
                f"Forensic signals ({types}) corroborated localized anomalies.",
            )

        if len(strong_votes) == 1:
            return (
                ForensicStatus.FORENSIC_SUSPICIOUS,
                ForensicAnomalyState.WEAK_ANOMALY,
                f"A notable forensic anomaly was detected ({strong_votes[0].signal_type.value}): {strong_votes[0].explanation}",
            )

        if len(weak_votes) >= 2:
            types = ", ".join(f.signal_type.value for f in weak_votes)
            return (
                ForensicStatus.FORENSIC_SUSPICIOUS,
                ForensicAnomalyState.WEAK_ANOMALY,
                f"Multiple moderate localized inconsistencies observed ({types}).",
            )

        if len(weak_votes) == 1:
            # Single weak vote alone: falls back to CLEAN (no single weak signal dominates)
            return (
                ForensicStatus.FORENSIC_CLEAN,
                ForensicAnomalyState.NO_FORENSIC_ANOMALY,
                f"Forensic analysis did not find systemic anomalies. An isolated weak variance ({weak_votes[0].signal_type.value}) is within normal capture tolerances.",
            )

        return (
            ForensicStatus.FORENSIC_CLEAN,
            ForensicAnomalyState.NO_FORENSIC_ANOMALY,
            "Forensic analysis did not identify digital manipulation anomalies across image quality, ELA, compression, copy-move, or boundary checks.",
        )

    def _resolve_profile(self, document_type: str, override: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], str]:
        """Fetch forensic configuration and version from DocumentProfile."""
        if override:
            return override, "override-1.0"

        try:
            profile = document_profile_registry.resolve(document_type)
            if profile and hasattr(profile, "forensic_config"):
                return profile.forensic_config or {}, getattr(profile, "version", "1.0.0")
        except Exception:
            pass
        return {}, "default-1.0"
