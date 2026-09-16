"""
backend/app/services/face/face_verification_service.py

High-level coordinator for Module 4: Biometric Face Verification & Presentation Attack Detection.

Pipeline Architecture:
  1. Image Decoding & Integrity Validation
  2. Document Face Localization (SCRFD with Haar fallback)
  3. Live Camera Face Localization (SCRFD with Haar fallback)
  4. Multiple-Face Isolation Gate (strictly aborts on >1 face)
  5. Deterministic Face Quality Gate (Blur, Luminance, Contrast, Resolution, Pose)
  6. Primary Deep Presentation Attack Detection (MiniFASNetV2)
  7. Secondary Optical Defensive Telemetry (2D FFT, YCrCb, HSV glare, temporal variance)
  8. Canonical 5-point ArcFace Landmark Alignment (112x112 similarity warp)
  9. Deep ArcFace Embedding Extraction (512-D L2-normalized unit vector)
 10. Cosine Similarity Vector Matching against configurable threshold
 11. Deterministic Decision Hierarchy Resolution

Design:
  - Document-agnostic architecture: operates on any document type (passport, visa, national ID).
  - Strict privacy: No persistent storage of raw biometric crops or 512-D vectors.
  - Zero fake scores: reports MODEL_UNAVAILABLE or BIOMETRIC_INCONCLUSIVE when models cannot run.
"""
from __future__ import annotations

import base64
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

def _crop_to_b64(crop_np: Optional[np.ndarray]) -> Optional[str]:
    if crop_np is None or not isinstance(crop_np, np.ndarray) or crop_np.size == 0:
        return None
    try:
        success, buf = cv2.imencode(".jpg", crop_np, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if success:
            return f"data:image/jpeg;base64,{base64.b64encode(buf.tobytes()).decode('ascii')}"
    except Exception:
        pass
    return None

from app.core.config import settings
from app.schemas.evidence import EvidenceModule, EvidenceSeverity, EvidenceStatus, NormalizedEvidenceItem
from app.schemas.face_verification import (
    AntiSpoofResult,
    DocumentFaceResult,
    FaceMatchResult,
    FaceQualityDetail,
    FaceVerificationResponse,
    LiveFaceResult,
    ModelInfoResponse,
    SecondaryPADSchema,
)
from app.services.face.arcface_embedding import ArcFaceEmbeddingModel
from app.services.face.face_aligner import FaceAligner
from app.services.face.face_detector import DetectedFaceBox, FaceDetector, face_detector
from app.services.face.face_enhancer import DocumentFaceEnhancer
from app.services.face.face_matcher import compare_face_embeddings
from app.services.face.face_quality import FaceQualityResult, evaluate_face_quality
from app.services.face.minifasnet_pad import MiniFASNetPAD
from app.services.face.secondary_pad import SecondaryOpticalPAD
from app.services.face.session_store import session_document_store
from app.services.risk.risk_session_store import risk_session_store

logger = logging.getLogger(__name__)

# Forensic/validation severities that trigger Dynamic Risk Tightening
# (Proprietary Enhancement D) when found in upstream M2/M3 evidence.
_ELEVATED_SEVERITIES = {"critical", "high"}
# Validation signal types that indicate the MRZ itself was structurally
# compromised — always elevation-worthy regardless of severity string casing
# used by the originating check.
_ELEVATED_VALIDATION_SIGNALS = {"mrz_auto_correction", "mrz_length_critical", "mrz_length_critical_failure"}
# Forensic signal/finding types that indicate deliberate digital tampering
# rather than routine capture-quality noise.
_ELEVATED_FORENSIC_SIGNALS = {
    "copy_move_duplication", "ai_tampering_model", "localized_tampering_region",
    "photo_boundary_fallback_variance_anomaly",
    "COPY_MOVE_DUPLICATION", "AI_TAMPERING_MODEL",
}


def _assess_upstream_risk(verification_id: str) -> tuple[bool, list[str]]:
    """
    Proprietary Enhancement D — Dynamic Risk Tightening.

    Read the shared risk_session_store for this verification session and
    determine whether M2 (validation) or M3 (forensics) already flagged
    tampering-relevant evidence. If so, the biometric engine must not treat
    this document the same as a clean one: the identity-matching threshold
    is tightened upward (see verify()) rather than left at its baseline.

    This function NEVER raises — a missing or malformed session must not
    block biometric verification; it simply means no elevation signal was
    found (fail toward the baseline threshold, not toward blocking
    processing entirely, since M2/M3 may legitimately not have run yet for
    some call patterns).

    Returns:
        (elevated, reasons) — elevated is True if ANY qualifying signal was
        found; reasons is a list of human-readable strings identifying
        which upstream module/signal triggered the escalation.
    """
    reasons: list[str] = []

    try:
        session = risk_session_store.get(verification_id)
    except Exception as exc:
        logger.debug("Dynamic Risk Tightening: could not read risk session for id=%s: %s", verification_id, exc)
        return False, reasons

    if not session:
        return False, reasons

    # ── M2 Validation ────────────────────────────────────────────────────
    m2 = session.get("m2_validation")
    if isinstance(m2, dict):
        for item in (m2.get("critical_evidence") or []):
            if not isinstance(item, dict):
                continue
            signal_type = str(item.get("signal_type", "")).lower()
            severity = str(item.get("severity", "")).lower()
            if signal_type in _ELEVATED_VALIDATION_SIGNALS or severity in _ELEVATED_SEVERITIES:
                reasons.append(f"m2_validation: {item.get('signal_type', 'critical_evidence')}")

        # Fall back to scanning `issues` in case a caller populated m2_validation
        # via an older/alternate path that predates the critical_evidence key.
        for issue in (m2.get("issues") or []):
            if not isinstance(issue, dict):
                continue
            check = str(issue.get("check", "")).lower()
            severity = str(issue.get("severity", "")).lower()
            if check in _ELEVATED_VALIDATION_SIGNALS and severity in ("critical", "failure"):
                reasons.append(f"m2_validation: {issue.get('check')}")

    # ── M3 Forensics (classical + advanced) ────────────────────────────────
    m3 = session.get("m3_forensics")
    if isinstance(m3, dict):
        for item in (m3.get("critical_evidence") or []):
            if not isinstance(item, dict):
                continue
            signal_type = str(item.get("signal_type", ""))
            severity = str(item.get("severity", "")).lower()
            if signal_type.lower() in {s.lower() for s in _ELEVATED_FORENSIC_SIGNALS} or severity in _ELEVATED_SEVERITIES:
                reasons.append(f"m3_forensics: {signal_type or 'critical_evidence'}")

        if str(m3.get("overall_assessment", "")).lower() == "high_forensic_concern":
            reasons.append("m3_forensics: overall_assessment=high_forensic_concern")

        advanced = m3.get("advanced_forensics")
        if isinstance(advanced, dict):
            if str(advanced.get("status", "")).lower() == "forensic_suspicious":
                reasons.append("m3_forensics.advanced: status=FORENSIC_SUSPICIOUS")
            for model_res in (advanced.get("model_results") or []):
                if isinstance(model_res, dict) and model_res.get("tampering_detected") is True:
                    reasons.append(f"m3_forensics.advanced: {model_res.get('model_name', 'ai_tampering_model')} flagged tampering")
            for finding in (advanced.get("findings") or []):
                if not isinstance(finding, dict):
                    continue
                f_type = str(finding.get("signal_type", ""))
                f_sev = str(finding.get("severity", "")).lower()
                if f_type in _ELEVATED_FORENSIC_SIGNALS and f_sev in _ELEVATED_SEVERITIES:
                    reasons.append(f"m3_forensics.advanced: {f_type}")

    # De-duplicate while preserving order
    seen: set[str] = set()
    unique_reasons = [r for r in reasons if not (r in seen or seen.add(r))]

    elevated = len(unique_reasons) > 0
    if elevated:
        logger.warning(
            "TRACKING_EVENT dynamic_risk_tightening: verification_id=%s reasons=%s",
            verification_id, unique_reasons,
        )

    return elevated, unique_reasons


class FaceVerificationService:
    """
    Enterprise biometric face verification service for border screening gates.
    Coordinates face detection, alignment, quality gating, anti-spoofing, and ArcFace matching.
    """

    def __init__(
        self,
        detector: Optional[FaceDetector] = None,
        embedding_model: Optional[ArcFaceEmbeddingModel] = None,
        pad_model: Optional[MiniFASNetPAD] = None,
    ) -> None:
        self.detector = detector or face_detector
        self.aligner = FaceAligner()
        self.embedding_model = embedding_model or ArcFaceEmbeddingModel()
        self.pad_model = pad_model or MiniFASNetPAD()
        self.secondary_pad = SecondaryOpticalPAD()

    def get_model_info(self) -> ModelInfoResponse:
        """Return non-sensitive model metadata for system auditability."""
        emb_info = self.embedding_model.model_info()
        pad_info = self.pad_model.model_info()
        return ModelInfoResponse(
            face_detector="InsightFace-SCRFD-10G (OpenCV Haar fallback)",
            detector_available=self.detector.is_ready(),
            face_embedding=emb_info.get("model_name", "ArcFace-w600k_r50"),
            embedding_dimension=emb_info.get("embedding_dimension", 512),
            embedding_available=self.embedding_model.is_available(),
            pad_model=pad_info.get("model_name", "MiniFASNetV2"),
            pad_available=self.pad_model.is_available(),
            face_match_threshold=settings.FACE_MATCH_THRESHOLD,
            pad_threshold=settings.ANTI_SPOOF_THRESHOLD,
        )

    def verify(
        self,
        verification_id: str,
        document_image_bytes: Any,
        live_frame_bytes: Any,
        sequence_frame_bytes: Optional[List[Any]] = None,
        document_type: str = "passport",
        portrait_region: Optional[Any] = None,
        document_profile: Optional[Any] = None,
        client_metadata: Optional[Dict[str, Any]] = None,
    ) -> FaceVerificationResponse:
        """
        Execute the end-to-end biometric verification workflow.
        Document-agnostic orchestration supporting profile-driven thresholds and M1 layout portrait isolation.
        """
        t0 = time.time()
        logger.info(
            "Starting biometric verification (session=%s, doc_type=%s, burst_frames=%d)",
            verification_id,
            document_type,
            len(sequence_frame_bytes) if sequence_frame_bytes else 0,
        )

        # ── 0. Security & Resource Limits (Hardware Safety) ────────────
        MAX_PAYLOAD_BYTES = 25 * 1024 * 1024  # 25MB
        MAX_DIMENSION = 10000                 # 10,000 pixels

        if isinstance(document_image_bytes, (bytes, bytearray)) and len(document_image_bytes) > MAX_PAYLOAD_BYTES:
            logger.warning("Document image payload (%d bytes) exceeds 25MB limit", len(document_image_bytes))
            return self._build_error_response(
                verification_id=verification_id,
                document_type=document_type,
                status="failed",
                overall="PROCESSING_ERROR",
                summary=f"Document image payload ({len(document_image_bytes)} bytes) exceeds security limit of 25MB.",
            )

        if isinstance(live_frame_bytes, (bytes, bytearray)) and len(live_frame_bytes) > MAX_PAYLOAD_BYTES:
            logger.warning("Live frame payload (%d bytes) exceeds 25MB limit", len(live_frame_bytes))
            return self._build_error_response(
                verification_id=verification_id,
                document_type=document_type,
                status="failed",
                overall="PROCESSING_ERROR",
                summary=f"Live camera frame payload ({len(live_frame_bytes)} bytes) exceeds security limit of 25MB.",
            )

        # Client trust boundary: any client claims regarding scores or liveness are strictly ignored
        if client_metadata:
            logger.debug("Client-supplied untrusted metadata ignored per security policy: %s", list(client_metadata.keys()))

        # ── 1. Image Decoding ─────────────────────────────────────────
        if isinstance(document_image_bytes, np.ndarray):
            doc_img = document_image_bytes
        elif isinstance(document_image_bytes, (bytes, bytearray)):
            doc_img = cv2.imdecode(np.frombuffer(document_image_bytes, np.uint8), cv2.IMREAD_COLOR)
        else:
            doc_img = None

        if isinstance(live_frame_bytes, np.ndarray):
            live_img = live_frame_bytes
        elif isinstance(live_frame_bytes, (bytes, bytearray)):
            live_img = cv2.imdecode(np.frombuffer(live_frame_bytes, np.uint8), cv2.IMREAD_COLOR)
        else:
            live_img = None

        if doc_img is None or live_img is None:
            logger.error("Failed to decode document or live frame bytes.")
            return self._build_error_response(
                verification_id=verification_id,
                document_type=document_type,
                status="failed",
                overall="PROCESSING_ERROR",
                summary="Failed to decode biometric image payloads.",
            )

        if max(doc_img.shape[:2]) > MAX_DIMENSION or max(live_img.shape[:2]) > MAX_DIMENSION:
            logger.warning("Biometric image dimensions exceed %d pixels limit", MAX_DIMENSION)
            return self._build_error_response(
                verification_id=verification_id,
                document_type=document_type,
                status="failed",
                overall="PROCESSING_ERROR",
                summary="Biometric image dimensions exceed maximum allowable limit of 10,000 pixels.",
            )

        # Resolve Document Profile
        profile = document_profile
        if profile is None:
            try:
                from app.services.documents.profiles import document_profile_registry
                profile = document_profile_registry.resolve(document_type)
            except Exception:
                profile = None

        # Check document profile applicability
        if profile is not None and not getattr(profile, "portrait_applicable", True):
            return self._build_document_face_missing_response(
                verification_id, document_type, "none", reason="biometric_not_applicable"
            )

        # ── 2. Document Face Localization & Fast-Path Cache ───────────
        cached_face = session_document_store.get_face_cache(verification_id)
        doc_aligned = None
        doc_embedding = None
        doc_source = "FULL_IMAGE_DETECTION"

        if cached_face is not None:
            doc_box = cached_face["doc_box"]
            doc_crop = cached_face["doc_crop"]
            doc_aligned = cached_face.get("doc_aligned")
            doc_embedding = cached_face.get("doc_embedding")
            doc_detector_used = cached_face.get("detector_used", "InsightFace-SCRFD-10G")
            doc_source = cached_face.get("source", "CACHED_PORTRAIT")
            doc_quality = evaluate_face_quality(doc_crop, is_document=True)
            logger.info("Fast-path: Reused cached document face for session=%s", verification_id)
        else:
            # 2a. Determine expected portrait region from arguments or profile
            exp_region = portrait_region
            if exp_region is None and profile is not None:
                if getattr(profile, "expected_semantic_regions", None) and "portrait" in profile.expected_semantic_regions:
                    exp_region = profile.expected_semantic_regions["portrait"].relative_box
                elif getattr(profile, "biometric_config", None) and "expected_portrait_region" in profile.biometric_config:
                    exp_region = profile.biometric_config["expected_portrait_region"]
                elif getattr(profile, "expected_regions", None) and "photo" in profile.expected_regions:
                    exp_region = profile.expected_regions["photo"]

            doc_box = None
            doc_detector_used = "none"

            if exp_region is not None:
                try:
                    if hasattr(exp_region, "ymin"):
                        ry1, rx1, ry2, rx2 = exp_region.ymin, exp_region.xmin, exp_region.ymax, exp_region.xmax
                    elif hasattr(exp_region, "x") and hasattr(exp_region, "y"):
                        rx1 = float(exp_region.x)
                        ry1 = float(exp_region.y)
                        rx2 = rx1 + float(getattr(exp_region, "width", 0.0))
                        ry2 = ry1 + float(getattr(exp_region, "height", 0.0))
                    elif isinstance(exp_region, (list, tuple)) and len(exp_region) == 4:
                        ry1, rx1, ry2, rx2 = exp_region
                    elif isinstance(exp_region, dict):
                        if "relative_x" in exp_region:
                            rx1 = exp_region["relative_x"]
                            ry1 = exp_region["relative_y"]
                            rx2 = rx1 + exp_region["relative_w"]
                            ry2 = ry1 + exp_region["relative_h"]
                        elif "ymin" in exp_region:
                            ry1, rx1, ry2, rx2 = exp_region["ymin"], exp_region["xmin"], exp_region["ymax"], exp_region["xmax"]
                        elif "x" in exp_region:
                            rx1 = exp_region["x"]
                            ry1 = exp_region["y"]
                            rx2 = rx1 + exp_region.get("width", 0.0)
                            ry2 = ry1 + exp_region.get("height", 0.0)
                        else:
                            ry1, rx1, ry2, rx2 = 0.0, 0.0, 1.0, 1.0
                    else:
                        ry1, rx1, ry2, rx2 = 0.0, 0.0, 1.0, 1.0

                    h_doc, w_doc = doc_img.shape[:2]
                    py1 = max(0, int(ry1 * h_doc))
                    px1 = max(0, int(rx1 * w_doc))
                    py2 = min(h_doc, int(ry2 * h_doc))
                    px2 = min(w_doc, int(rx2 * w_doc))

                    if (py2 - py1) >= 30 and (px2 - px1) >= 30:
                        region_crop = doc_img[py1:py2, px1:px2]
                        r_detect = self.detector.detect_faces(region_crop, is_document=True)
                        if r_detect.face_count == 1:
                            raw_box = r_detect.faces[0]
                            mapped_box = DetectedFaceBox(
                                x=px1 + raw_box.x,
                                y=py1 + raw_box.y,
                                width=raw_box.width,
                                height=raw_box.height,
                                confidence=raw_box.confidence,
                            )
                            if raw_box.landmarks:
                                mapped_box.landmarks = [(px1 + lx, py1 + ly) for (lx, ly) in raw_box.landmarks]
                            doc_box = mapped_box
                            doc_source = "DOCUMENT_PORTRAIT_REGION"
                            doc_detector_used = r_detect.detector_used
                        elif r_detect.face_count > 1:
                            logger.warning("Multiple faces (%d) detected in document portrait region", r_detect.face_count)
                            return self._build_multiple_faces_response(
                                verification_id, document_type, is_document=True, count=r_detect.face_count
                            )
                except Exception as _reg_exc:
                    logger.debug("Portrait region search exception: %s", _reg_exc)

            # 2b. Safe fallback to full document detection if region search did not isolate a face
            if doc_box is None:
                doc_detect = self.detector.detect_faces(doc_img, is_document=True)
                if doc_detect.face_count == 0:
                    logger.warning("No face detected on document (session=%s)", verification_id)
                    return self._build_document_face_missing_response(
                        verification_id, document_type, doc_detect.detector_used
                    )

                if doc_detect.face_count > 1:
                    logger.warning("Multiple faces (%d) detected on document", doc_detect.face_count)
                    return self._build_multiple_faces_response(
                        verification_id, document_type, is_document=True, count=doc_detect.face_count
                    )

                doc_box = doc_detect.faces[0]
                doc_source = "FULL_IMAGE_DETECTION"
                doc_detector_used = doc_detect.detector_used

            # Extract portrait crop with balanced margins (with mock fallback to crop_face)
            doc_crop_candidate = getattr(self.detector, "crop_portrait", self.detector.crop_face)(doc_img, doc_box)
            if isinstance(doc_crop_candidate, np.ndarray):
                doc_crop_raw = doc_crop_candidate
            else:
                doc_crop_raw = self.detector.crop_face(doc_img, doc_box)
            # Inbuilt Super-Resolution & Quality Enhancement Layer
            doc_crop = DocumentFaceEnhancer.enhance_portrait_crop(doc_crop_raw)
            doc_quality = evaluate_face_quality(doc_crop, is_document=True)

        # ── 3. Live Camera Face Localization ──────────────────────────
        live_detect = self.detector.detect_faces(live_img, is_document=False)
        if live_detect.face_count == 0:
            logger.warning("No face detected in live capture (session=%s)", verification_id)
            return self._build_live_face_missing_response(
                verification_id, document_type, doc_quality, doc_detector_used, live_detect.detector_used
            )

        if live_detect.face_count > 1:
            logger.warning("Multiple faces (%d) detected in live feed", live_detect.face_count)
            return self._build_multiple_faces_response(
                verification_id, document_type, is_document=False, count=live_detect.face_count
            )

        live_box = live_detect.faces[0]
        live_source = "LIVE_CAPTURE"
        live_crop = self.detector.crop_face(live_img, live_box)
        live_quality = evaluate_face_quality(live_crop, is_document=False)

        # ── 4. Decode Sequence Frames for Temporal PAD ────────────────
        sequence_items = []
        sequence_crops = []
        if sequence_frame_bytes:
            for b in sequence_frame_bytes:
                if isinstance(b, np.ndarray):
                    s_img = b
                elif isinstance(b, (bytes, bytearray)):
                    s_img = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
                else:
                    s_img = None
                if s_img is not None:
                    # Fast sequence crop reusing anchor live_box
                    s_crop = self.detector.crop_face(s_img, live_box)
                    sequence_items.append((s_crop, live_box.bbox, s_img))
                    sequence_crops.append(s_crop)

        # ── 5. Quality Gate Evaluation ────────────────────────────────
        if not doc_quality.is_acceptable or not live_quality.is_acceptable:
            logger.warning(
                "Face quality gate failed (doc_acceptable=%s, live_acceptable=%s)",
                doc_quality.is_acceptable,
                live_quality.is_acceptable,
            )
            return self._build_poor_quality_response(
                verification_id=verification_id,
                document_type=document_type,
                doc_q=doc_quality,
                live_q=live_quality,
                doc_det=doc_detector_used,
                live_det=live_detect.detector_used,
                doc_box=doc_box,
                doc_source=doc_source,
                doc_shape=doc_img.shape[:2],
                live_box=live_box,
                live_source=live_source,
                live_shape=live_img.shape[:2],
            )

        # ── 6. Presentation Attack Detection (Primary + Secondary) ────
        if sequence_items:
            # Multi-frame temporal assessment
            primary_items = [(live_crop, live_box.bbox, live_img)] + sequence_items
            pad_result = self.pad_model.predict_sequence(primary_items)
        else:
            pad_result = self.pad_model.predict(live_crop, bbox=live_box.bbox, original_img=live_img)

        # Secondary defensive optical telemetry
        secondary_pad_res = self.secondary_pad.analyze(live_crop, sequence_crops=sequence_crops)

        logger.info(
            "PAD completed: status=%s, score=%s, model=%s",
            pad_result.status,
            pad_result.score,
            pad_result.model_name,
        )

        # ── 7. Face Alignment to ArcFace Canonical Template ───────────
        try:
            if doc_aligned is None:
                if doc_box.landmarks and len(doc_box.landmarks) == 5:
                    doc_aligned = self.aligner.align_face_5point(doc_img, doc_box.landmarks, (112, 112))
                else:
                    doc_aligned = self.aligner.align_bbox_fallback(doc_img, doc_box.bbox, target_size=(112, 112))

            if live_box.landmarks and len(live_box.landmarks) == 5:
                live_aligned = self.aligner.align_face_5point(live_img, live_box.landmarks, (112, 112))
            else:
                live_aligned = self.aligner.align_bbox_fallback(live_img, live_box.bbox, target_size=(112, 112))
        except Exception as exc:
            logger.error("Face alignment failed: %s", exc)
            return self._build_error_response(
                verification_id=verification_id,
                document_type=document_type,
                status="failed",
                overall="PROCESSING_ERROR",
                summary=f"Face alignment error: {exc}",
            )

        # ── 8. ArcFace 512-D Embedding Extraction ─────────────────────
        if not self.embedding_model.is_available():
            logger.error("ArcFace model unavailable for embedding extraction.")
            return self._build_model_unavailable_response(
                verification_id=verification_id,
                document_type=document_type,
                doc_q=doc_quality,
                live_q=live_quality,
                pad_res=pad_result,
                sec_pad=secondary_pad_res,
                doc_box=doc_box,
                doc_source=doc_source,
                doc_shape=doc_img.shape[:2],
                live_box=live_box,
                live_source=live_source,
                live_shape=live_img.shape[:2],
                doc_det=doc_detector_used,
                live_det=live_detect.detector_used,
            )

        try:
            if doc_embedding is None:
                # Enhance document facial contrast and suppress print/scanning noise for robust cross-domain matching
                doc_aligned_enh = self.aligner.enhance_document_face(doc_aligned)
                doc_embedding = self.embedding_model.get_embedding(doc_aligned_enh)
            live_embedding = self.embedding_model.get_embedding(live_aligned)
        except Exception as exc:
            logger.error("Embedding generation failed: %s", exc)
            return self._build_error_response(
                verification_id=verification_id,
                document_type=document_type,
                status="failed",
                overall="PROCESSING_ERROR",
                summary=f"Feature extraction failure: {exc}",
            )

        # Store pre-extracted document features in ephemeral cache for instantaneous re-verifications
        if cached_face is None:
            session_document_store.set_face_cache(
                verification_id=verification_id,
                doc_box=doc_box,
                doc_crop=doc_crop,
                doc_aligned=doc_aligned,
                doc_embedding=doc_embedding,
                detector_used=doc_detector_used,
            )

        # Profile-driven threshold & calibration overrides
        face_match_threshold = settings.FACE_MATCH_THRESHOLD
        calib_status = settings.FACE_MATCH_CALIBRATION_STATUS
        inconclusive_margin = 0.06

        if profile is not None and getattr(profile, "biometric_config", None):
            b_cfg = profile.biometric_config
            face_match_threshold = b_cfg.get("face_match_threshold", face_match_threshold)
            calib_status = b_cfg.get("calibration_status", calib_status)
            inconclusive_margin = b_cfg.get("inconclusive_margin", inconclusive_margin)

        # ── 8b. Dynamic Risk Tightening (Proprietary Enhancement D) ────
        # If upstream M2 (validation) already found the MRZ was auto-corrected
        # or critically malformed, or M3 (forensics — classical or advanced
        # engine) raised a CRITICAL/HIGH tampering signal, this document is
        # already known-suspicious. It must clear a materially stricter
        # identity bar than a clean document before a biometric match is
        # accepted — never the same uncalibrated baseline. The elevated
        # threshold is applied as a floor: it can only raise the operating
        # threshold, never lower a profile-specific threshold that was
        # already stricter than the elevated ceiling.
        risk_elevated, risk_reasons = _assess_upstream_risk(verification_id)
        if risk_elevated:
            pre_elevation_threshold = face_match_threshold
            face_match_threshold = max(face_match_threshold, settings.FACE_MATCH_THRESHOLD_ELEVATED)
            calib_status = "CALIBRATED_RISK_ELEVATED"
            logger.warning(
                "Dynamic Risk Tightening applied: id=%s threshold %.2f -> %.2f reasons=%s",
                verification_id, pre_elevation_threshold, face_match_threshold, risk_reasons,
            )

        # ── 9. Cosine Similarity Matching ─────────────────────────────
        match_result = compare_face_embeddings(
            doc_embedding,
            live_embedding,
            threshold=face_match_threshold,
            calibration_status=calib_status,
            inconclusive_margin=inconclusive_margin,
            risk_escalated=risk_elevated,
            risk_escalation_reasons=risk_reasons,
        )

        # ── 10. Decision Hierarchy Resolution ─────────────────────────
        overall_status = "BIOMETRIC_INCONCLUSIVE"
        summary = ""

        if pad_result.status == "suspected_spoof":
            overall_status = "SUSPECTED_SPOOF"
            summary = "Presentation attack detected. Liveness check failed; facial matching suspended."
        elif pad_result.status == "model_unavailable":
            overall_status = "BIOMETRIC_INCONCLUSIVE"
            summary = "PAD model unavailable. Cannot confirm physical liveness."
        elif pad_result.status == "inconclusive":
            overall_status = "BIOMETRIC_INCONCLUSIVE"
            summary = "Presentation attack analysis inconclusive. Manual officer inspection advised."
        elif match_result.status == "match":
            overall_status = "FACE_MATCH"
            summary = (
                f"Facial verification successful: live subject matches document photograph "
                f"(similarity: {match_result.similarity:.3f}, threshold: {match_result.threshold:.2f})."
            )
        elif match_result.status == "no_match":
            overall_status = "FACE_MISMATCH"
            summary = (
                f"Facial mismatch: live subject does not match document photograph "
                f"(similarity: {match_result.similarity:.3f} < {match_result.threshold:.2f})."
            )
        else:
            overall_status = "BIOMETRIC_INCONCLUSIVE"
            summary = "Facial comparison inconclusive."

        # ── Requirement #5: escalated evidence for a match failure that occurred
        # under Dynamic Risk Tightening ────────────────────────────────────────
        # A NormalizedEvidenceItem is raised specifically (and only) when the
        # match failed/was inconclusive WHILE the threshold was elevated —
        # this is the case that most needs an explicit record, since the same
        # similarity score might have cleared the unelevated baseline. The
        # evidence explicitly states the failure was escalated by upstream
        # forensic/validation risk priors, not a routine biometric mismatch.
        biometric_evidence_items: list[NormalizedEvidenceItem] = []
        if risk_elevated and match_result.status in ("no_match", "inconclusive"):
            escalation_desc = (
                f"Facial biometric {match_result.status.replace('_', ' ')} occurred under a "
                f"dynamically TIGHTENED identity threshold ({match_result.threshold:.2f}, raised from "
                f"baseline {settings.FACE_MATCH_THRESHOLD:.2f}) because upstream evidence already flagged "
                f"this document as elevated risk: {'; '.join(risk_reasons)}. This biometric failure was "
                f"ESCALATED by upstream forensic/validation risk priors — it is reported as a compounding "
                f"signal on an already-suspicious document, not an isolated biometric result."
            )
            biometric_evidence_items.append(
                NormalizedEvidenceItem(
                    document_id=verification_id,
                    document_type=document_type,
                    module=EvidenceModule.BIOMETRICS,
                    signal_type="biometric_match_failed_under_risk_escalation",
                    status=EvidenceStatus.FAILED if match_result.status == "no_match" else EvidenceStatus.SUSPICIOUS,
                    severity=EvidenceSeverity.HIGH if match_result.status == "no_match" else EvidenceSeverity.MEDIUM,
                    confidence=float(match_result.confidence_score) if match_result.confidence_score is not None else 0.5,
                    description=escalation_desc,
                    source="face_verification_service.dynamic_risk_tightening",
                    module_version="1.1.0",
                    provenance={
                        "similarity": match_result.similarity,
                        "baseline_threshold": settings.FACE_MATCH_THRESHOLD,
                        "elevated_threshold": match_result.threshold,
                        "escalation_reasons": risk_reasons,
                    },
                )
            )
            summary += f" [ESCALATED: {escalation_desc}]"
            logger.warning(
                "TRACKING_EVENT biometric_failure_escalated_by_risk: id=%s match_status=%s reasons=%s",
                verification_id, match_result.status, risk_reasons,
            )

        elapsed_ms = (time.time() - t0) * 1000.0
        logger.info(
            "Biometric verification completed in %.1fms (status=%s, match=%s, pad=%s, risk_elevated=%s)",
            elapsed_ms,
            overall_status,
            match_result.status,
            pad_result.status,
            risk_elevated,
        )

        # Build evidence payloads
        doc_face_res = self._to_doc_face_result(
            doc_quality, doc_detector_used, box=doc_box, source=doc_source, img_shape=doc_img.shape[:2]
        )
        live_face_res = self._to_live_face_result(
            live_quality, live_detect.detector_used, box=live_box, source=live_source, img_shape=live_img.shape[:2]
        )

        doc_portrait_ev = {
            "source": doc_source,
            "detected": doc_face_res.detected,
            "face_count": doc_face_res.face_count,
            "bbox": doc_face_res.bbox,
            "normalized_bbox": doc_face_res.normalized_bbox,
            "landmarks": doc_face_res.landmarks,
            "quality": doc_face_res.quality,
            "detector_used": doc_face_res.detector_used,
        }

        live_face_ev = {
            "source": live_source,
            "detected": live_face_res.detected,
            "face_count": live_face_res.face_count,
            "bbox": live_face_res.bbox,
            "normalized_bbox": live_face_res.normalized_bbox,
            "landmarks": live_face_res.landmarks,
            "quality": live_face_res.quality,
            "detector_used": live_face_res.detector_used,
        }

        pad_ev = {
            "model": pad_result.model_name,
            "model_version": "2.0.0",
            "status": pad_result.status,
            "score": pad_result.score,
            "explanation": pad_result.explanation,
            "details": pad_result.details,
        }

        sim_val = getattr(match_result, "similarity", None)
        sim_sc = getattr(match_result, "confidence_score", None)
        if sim_sc is None:
            sim_sc = getattr(match_result, "similarity_score", sim_val)
        thresh_val = getattr(match_result, "threshold", face_match_threshold)
        calib_val = getattr(match_result, "threshold_calibration", calib_status)
        metric_val = getattr(match_result, "similarity_metric", "cosine")
        match_expl = getattr(match_result, "explanation", "")

        comp_ev = {
            "status": getattr(match_result, "status", "unknown"),
            "similarity": sim_val,
            "similarity_score": sim_sc,
            "threshold": thresh_val,
            "threshold_calibration": calib_val,
            "similarity_metric": metric_val,
            "explanation": match_expl,
            "risk_escalated": risk_elevated,
            "risk_escalation_reasons": risk_reasons,
        }

        model_meta = {
            "face_detector": doc_detector_used,
            "embedding_model": self.embedding_model.model_info().get("model_name", "ArcFace-w600k_r50"),
            "embedding_dimension": self.embedding_model.get_embedding_dimension(),
            "pad_model": pad_result.model_name,
        }

        return FaceVerificationResponse(
            verification_id=verification_id,
            document_type=document_type,
            status="completed",
            overall_assessment=overall_status,
            overall_biometric_status=overall_status,
            document_face=doc_face_res,
            live_face=live_face_res,
            anti_spoof=AntiSpoofResult(
                model=pad_result.model_name,
                model_version="2.0.0",
                status=pad_result.status,
                score=pad_result.score,
                explanation=pad_result.explanation,
                details=pad_result.details,
            ),
            secondary_pad=SecondaryPADSchema(
                frequency_domain=secondary_pad_res.frequency_domain,
                texture_analysis=secondary_pad_res.texture_analysis,
                specular_glare=secondary_pad_res.specular_glare,
                temporal_variance=secondary_pad_res.temporal_variance,
            ),
            face_match=FaceMatchResult(
                status=getattr(match_result, "status", "unknown"),
                similarity=sim_val,
                similarity_score=sim_sc,
                threshold=thresh_val,
                threshold_calibration=calib_val,
                similarity_metric=metric_val,
                embedding_model=self.embedding_model.model_info().get("model_name", "ArcFace-w600k_r50"),
                embedding_dimension=self.embedding_model.get_embedding_dimension(),
                explanation=match_expl,
                risk_escalated=risk_elevated,
                risk_escalation_reasons=risk_reasons,
            ),
            document_face_image=_crop_to_b64(doc_crop),
            live_face_image=_crop_to_b64(live_crop),
            summary=summary,
            document_portrait=doc_portrait_ev,
            live_face_evidence=live_face_ev,
            pad_evidence=pad_ev,
            comparison_evidence=comp_ev,
            model_metadata=model_meta,
            profile_version=profile.version if profile else "default",
            biometric_engine_version="1.1.0",
            evidence_items=biometric_evidence_items,
        )

    # ── Helpers for Non-Nominal Response Scenarios ─────────────────────

    def _build_document_face_missing_response(
        self,
        verification_id: str,
        document_type: str,
        detector_name: str,
        reason: Optional[str] = None,
    ) -> FaceVerificationResponse:
        if reason == "biometric_not_applicable" or document_type.lower() == "visa":
            return FaceVerificationResponse(
                verification_id=verification_id,
                document_type=document_type,
                status="completed",
                overall_assessment="NOT_APPLICABLE",
                overall_biometric_status="NOT_APPLICABLE",
                document_face=DocumentFaceResult(
                    detected=False,
                    face_count=0,
                    quality="unavailable",
                    detector_used=detector_name,
                    error=None,
                ),
                live_face=LiveFaceResult(detected=False, face_count=0, quality="unavailable"),
                anti_spoof=AntiSpoofResult(
                    status="inconclusive", score=None, explanation=f"Biometrics not applicable for this {document_type} profile."
                ),
                secondary_pad=SecondaryPADSchema(
                    frequency_domain="inconclusive",
                    texture_analysis="inconclusive",
                    specular_glare="inconclusive",
                    temporal_variance="inconclusive",
                ),
                face_match=FaceMatchResult(
                    status="unavailable",
                    similarity=None,
                    similarity_score=None,
                    threshold=settings.FACE_MATCH_THRESHOLD,
                    explanation=f"No usable portrait region was identified for this {document_type} profile.",
                ),
                summary=f"Biometric verification not applicable: No usable portrait region was identified for this {document_type} profile.",
            )

        return FaceVerificationResponse(
            verification_id=verification_id,
            document_type=document_type,
            status="failed",
            overall_assessment="DOCUMENT_FACE_NOT_FOUND",
            overall_biometric_status="DOCUMENT_FACE_NOT_FOUND",
            document_face=DocumentFaceResult(
                detected=False,
                face_count=0,
                quality="unavailable",
                detector_used=detector_name,
                error="DOCUMENT_FACE_NOT_FOUND",
            ),
            live_face=LiveFaceResult(detected=False, face_count=0, quality="unavailable"),
            anti_spoof=AntiSpoofResult(
                status="model_unavailable", score=None, explanation="No live face evaluated."
            ),
            secondary_pad=SecondaryPADSchema(
                frequency_domain="inconclusive",
                texture_analysis="inconclusive",
                specular_glare="inconclusive",
                temporal_variance="inconclusive",
            ),
            face_match=FaceMatchResult(
                status="unavailable",
                similarity=None,
                similarity_score=None,
                threshold=settings.FACE_MATCH_THRESHOLD,
                explanation="Document portrait not found.",
            ),
            summary="No face could be localized on the identity document photograph.",
        )

    def _build_live_face_missing_response(
        self,
        verification_id: str,
        document_type: str,
        doc_quality: FaceQualityResult,
        doc_det_name: str,
        live_det_name: str,
    ) -> FaceVerificationResponse:
        return FaceVerificationResponse(
            verification_id=verification_id,
            document_type=document_type,
            status="failed",
            overall_assessment="NO_FACE_DETECTED",
            overall_biometric_status="NO_FACE_DETECTED",
            document_face=self._to_doc_face_result(doc_quality, doc_det_name),
            live_face=LiveFaceResult(
                detected=False,
                face_count=0,
                quality="unavailable",
                detector_used=live_det_name,
                error="FACE_NOT_DETECTED",
            ),
            anti_spoof=AntiSpoofResult(
                status="inconclusive", score=None, explanation="No live face detected."
            ),
            secondary_pad=SecondaryPADSchema(
                frequency_domain="inconclusive",
                texture_analysis="inconclusive",
                specular_glare="inconclusive",
                temporal_variance="inconclusive",
            ),
            face_match=FaceMatchResult(
                status="unavailable",
                similarity=None,
                similarity_score=None,
                threshold=settings.FACE_MATCH_THRESHOLD,
                explanation="Live traveler face not detected.",
            ),
            summary="No face detected in the live camera capture. Position face inside the target frame.",
        )

    def _build_multiple_faces_response(
        self, verification_id: str, document_type: str, is_document: bool, count: int
    ) -> FaceVerificationResponse:
        err_target = "document" if is_document else "live camera feed"
        msg = f"Multiple faces ({count}) detected in {err_target}. Exactly one face must be present."
        return FaceVerificationResponse(
            verification_id=verification_id,
            document_type=document_type,
            status="failed",
            overall_assessment="MULTIPLE_FACES_DETECTED",
            overall_biometric_status="MULTIPLE_FACES_DETECTED",
            document_face=DocumentFaceResult(
                detected=is_document,
                face_count=count if is_document else 1,
                quality="unavailable" if is_document else "acceptable",
                error="MULTIPLE_FACES_DETECTED" if is_document else None,
            ),
            live_face=LiveFaceResult(
                detected=not is_document,
                face_count=count if not is_document else 1,
                quality="unavailable" if not is_document else "acceptable",
                error="MULTIPLE_FACES_DETECTED" if not is_document else None,
            ),
            anti_spoof=AntiSpoofResult(
                status="inconclusive", score=None, explanation="Multiple faces present; anti-spoof suspended."
            ),
            secondary_pad=SecondaryPADSchema(
                frequency_domain="inconclusive",
                texture_analysis="inconclusive",
                specular_glare="inconclusive",
                temporal_variance="inconclusive",
            ),
            face_match=FaceMatchResult(
                status="unavailable",
                similarity=None,
                similarity_score=None,
                threshold=settings.FACE_MATCH_THRESHOLD,
                explanation="Verification suspended due to multiple faces in frame.",
            ),
            summary=msg,
        )

    def _build_poor_quality_response(
        self,
        verification_id: str,
        document_type: str,
        doc_q: FaceQualityResult,
        live_q: FaceQualityResult,
        doc_det: str,
        live_det: str,
        doc_box: Optional[Any] = None,
        doc_source: str = "FULL_IMAGE_DETECTION",
        doc_shape: Optional[Tuple[int, int]] = None,
        live_box: Optional[Any] = None,
        live_source: str = "LIVE_CAPTURE",
        live_shape: Optional[Tuple[int, int]] = None,
    ) -> FaceVerificationResponse:
        reasons = []
        if not doc_q.is_acceptable:
            reasons.append(f"document face quality poor ({doc_q.explanation})")
        if not live_q.is_acceptable:
            reasons.append(f"live capture quality poor ({live_q.explanation})")
        msg = "Biometric quality gate failed: " + "; ".join(reasons)

        doc_face_res = self._to_doc_face_result(doc_q, doc_det, box=doc_box, source=doc_source, img_shape=doc_shape)
        live_face_res = self._to_live_face_result(live_q, live_det, box=live_box, source=live_source, img_shape=live_shape)

        doc_portrait_ev = {
            "source": doc_source,
            "detected": doc_face_res.detected,
            "face_count": doc_face_res.face_count,
            "bbox": doc_face_res.bbox,
            "normalized_bbox": doc_face_res.normalized_bbox,
            "landmarks": doc_face_res.landmarks,
            "quality": doc_face_res.quality,
            "detector_used": doc_face_res.detector_used,
        }

        live_face_ev = {
            "source": live_source,
            "detected": live_face_res.detected,
            "face_count": live_face_res.face_count,
            "bbox": live_face_res.bbox,
            "normalized_bbox": live_face_res.normalized_bbox,
            "landmarks": live_face_res.landmarks,
            "quality": live_face_res.quality,
            "detector_used": live_face_res.detector_used,
        }

        return FaceVerificationResponse(
            verification_id=verification_id,
            document_type=document_type,
            status="failed",
            overall_assessment="POOR_QUALITY",
            overall_biometric_status="POOR_QUALITY",
            document_face=doc_face_res,
            live_face=live_face_res,
            anti_spoof=AntiSpoofResult(
                status="inconclusive", score=None, explanation="Quality insufficient for reliable PAD."
            ),
            secondary_pad=SecondaryPADSchema(
                frequency_domain="inconclusive",
                texture_analysis="inconclusive",
                specular_glare="inconclusive",
                temporal_variance="inconclusive",
            ),
            face_match=FaceMatchResult(
                status="unavailable",
                similarity=None,
                similarity_score=None,
                threshold=settings.FACE_MATCH_THRESHOLD,
                explanation="Biometric match suspended due to low facial image quality.",
            ),
            document_portrait=doc_portrait_ev,
            live_face_evidence=live_face_ev,
            summary=msg,
        )

    def _build_model_unavailable_response(
        self,
        verification_id: str,
        document_type: str,
        doc_q: FaceQualityResult,
        live_q: FaceQualityResult,
        pad_res,
        sec_pad,
        doc_box: Optional[Any] = None,
        doc_source: str = "FULL_IMAGE_DETECTION",
        doc_shape: Optional[Tuple[int, int]] = None,
        live_box: Optional[Any] = None,
        live_source: str = "LIVE_CAPTURE",
        live_shape: Optional[Tuple[int, int]] = None,
        doc_det: str = "InsightFace-SCRFD",
        live_det: str = "InsightFace-SCRFD",
    ) -> FaceVerificationResponse:
        doc_face_res = self._to_doc_face_result(doc_q, doc_det, box=doc_box, source=doc_source, img_shape=doc_shape)
        live_face_res = self._to_live_face_result(live_q, live_det, box=live_box, source=live_source, img_shape=live_shape)

        doc_portrait_ev = {
            "source": doc_source,
            "detected": doc_face_res.detected,
            "face_count": doc_face_res.face_count,
            "bbox": doc_face_res.bbox,
            "normalized_bbox": doc_face_res.normalized_bbox,
            "landmarks": doc_face_res.landmarks,
            "quality": doc_face_res.quality,
            "detector_used": doc_face_res.detector_used,
        }

        live_face_ev = {
            "source": live_source,
            "detected": live_face_res.detected,
            "face_count": live_face_res.face_count,
            "bbox": live_face_res.bbox,
            "normalized_bbox": live_face_res.normalized_bbox,
            "landmarks": live_face_res.landmarks,
            "quality": live_face_res.quality,
            "detector_used": live_face_res.detector_used,
        }

        return FaceVerificationResponse(
            verification_id=verification_id,
            document_type=document_type,
            status="model_unavailable",
            overall_assessment="MODEL_UNAVAILABLE",
            overall_biometric_status="BIOMETRIC_INCONCLUSIVE",
            document_face=doc_face_res,
            live_face=live_face_res,
            anti_spoof=AntiSpoofResult(
                model=pad_res.model_name,
                status=pad_res.status,
                score=pad_res.score,
                explanation=pad_res.explanation,
            ),
            secondary_pad=SecondaryPADSchema(
                frequency_domain=sec_pad.frequency_domain,
                texture_analysis=sec_pad.texture_analysis,
                specular_glare=sec_pad.specular_glare,
                temporal_variance=sec_pad.temporal_variance,
            ),
            face_match=FaceMatchResult(
                status="unavailable",
                similarity=None,
                similarity_score=None,
                threshold=settings.FACE_MATCH_THRESHOLD,
                explanation="ArcFace model weights are unavailable on server.",
            ),
            document_portrait=doc_portrait_ev,
            live_face_evidence=live_face_ev,
            summary="Biometric models are unavailable on server. Facial verification inconclusive.",
        )

    def _build_error_response(
        self, verification_id: str, document_type: str, status: str, overall: str, summary: str
    ) -> FaceVerificationResponse:
        return FaceVerificationResponse(
            verification_id=verification_id,
            document_type=document_type,
            status=status,
            overall_assessment=overall,
            overall_biometric_status=overall,
            document_face=DocumentFaceResult(detected=False, face_count=0, quality="unavailable"),
            live_face=LiveFaceResult(detected=False, face_count=0, quality="unavailable"),
            anti_spoof=AntiSpoofResult(status="inconclusive", score=None, explanation="Processing error."),
            secondary_pad=SecondaryPADSchema(
                frequency_domain="inconclusive",
                texture_analysis="inconclusive",
                specular_glare="inconclusive",
                temporal_variance="inconclusive",
            ),
            face_match=FaceMatchResult(
                status="unavailable",
                similarity=None,
                similarity_score=None,
                threshold=settings.FACE_MATCH_THRESHOLD,
                explanation="Processing error.",
            ),
            summary=summary,
        )

    @staticmethod
    def _to_doc_face_result(
        q: FaceQualityResult,
        det_name: str,
        box: Optional[Any] = None,
        source: Optional[str] = None,
        img_shape: Optional[Tuple[int, int]] = None,
    ) -> DocumentFaceResult:
        detail = FaceQualityDetail(
            status=q.status,
            blur=q.blur,
            brightness=q.brightness,
            contrast=q.contrast,
            face_size=q.face_size,
            pose=q.pose,
            explanation=q.explanation,
        )
        bbox = box.bbox if box is not None and hasattr(box, "bbox") else None
        landmarks = box.landmarks if box is not None and hasattr(box, "landmarks") else None
        conf = box.confidence if box is not None and hasattr(box, "confidence") else None
        norm_bbox = None
        if box is not None and img_shape is not None and hasattr(box, "get_normalized_bbox"):
            norm_bbox = box.get_normalized_bbox(img_shape[0], img_shape[1])
        elif box is not None and img_shape is not None and hasattr(box, "x"):
            norm_bbox = (
                round(max(0.0, min(1.0, box.y / max(img_shape[0], 1))), 4),
                round(max(0.0, min(1.0, box.x / max(img_shape[1], 1))), 4),
                round(max(0.0, min(1.0, (box.y + box.height) / max(img_shape[0], 1))), 4),
                round(max(0.0, min(1.0, (box.x + box.width) / max(img_shape[1], 1))), 4),
            )

        return DocumentFaceResult(
            detected=True,
            face_count=1,
            quality=q.status,
            quality_details=detail,
            detector_used=det_name,
            error=q.error_code,
            source=source or "FULL_IMAGE_DETECTION",
            bbox=bbox,
            normalized_bbox=norm_bbox,
            landmarks=landmarks,
            detection_confidence=conf,
        )

    @staticmethod
    def _to_live_face_result(
        q: FaceQualityResult,
        det_name: str,
        box: Optional[Any] = None,
        source: Optional[str] = None,
        img_shape: Optional[Tuple[int, int]] = None,
    ) -> LiveFaceResult:
        detail = FaceQualityDetail(
            status=q.status,
            blur=q.blur,
            brightness=q.brightness,
            contrast=q.contrast,
            face_size=q.face_size,
            pose=q.pose,
            explanation=q.explanation,
        )
        bbox = box.bbox if box is not None and hasattr(box, "bbox") else None
        landmarks = box.landmarks if box is not None and hasattr(box, "landmarks") else None
        conf = box.confidence if box is not None and hasattr(box, "confidence") else None
        norm_bbox = None
        if box is not None and img_shape is not None and hasattr(box, "get_normalized_bbox"):
            norm_bbox = box.get_normalized_bbox(img_shape[0], img_shape[1])
        elif box is not None and img_shape is not None and hasattr(box, "x"):
            norm_bbox = (
                round(max(0.0, min(1.0, box.y / max(img_shape[0], 1))), 4),
                round(max(0.0, min(1.0, box.x / max(img_shape[1], 1))), 4),
                round(max(0.0, min(1.0, (box.y + box.height) / max(img_shape[0], 1))), 4),
                round(max(0.0, min(1.0, (box.x + box.width) / max(img_shape[1], 1))), 4),
            )

        return LiveFaceResult(
            detected=True,
            face_count=1,
            quality=q.status,
            quality_details=detail,
            detector_used=det_name,
            error=q.error_code,
            source=source or "LIVE_CAPTURE",
            bbox=bbox,
            normalized_bbox=norm_bbox,
            landmarks=landmarks,
            detection_confidence=conf,
        )


face_verification_service = FaceVerificationService()


def verify_passport_biometrics(
    *args,
    **kwargs,
) -> FaceVerificationResponse:
    """
    Convenience function for biometric verification supporting both positional and keyword invocations.
    """
    verification_id = kwargs.get("verification_id")
    document_type = kwargs.get("document_type", "passport")
    doc_img = kwargs.get("doc_image_bytes") or kwargs.get("document_image_bytes") or kwargs.get("document_image_bgr")
    live_img = kwargs.get("live_face_bytes") or kwargs.get("live_frame_bytes") or kwargs.get("live_frame_bgr")
    sequence_frames = kwargs.get("sequence_frame_bytes") or kwargs.get("sequence_frames_bgr")
    portrait_region = kwargs.get("portrait_region")
    document_profile = kwargs.get("document_profile")
    client_metadata = kwargs.get("client_metadata")

    if len(args) > 0:
        if isinstance(args[0], str) and (len(args) > 1 and isinstance(args[1], str)):
            # Standard positional: (verification_id, document_type, doc_img, live_img, [seq])
            verification_id = args[0]
            document_type = args[1]
            if len(args) > 2:
                doc_img = args[2]
            if len(args) > 3:
                live_img = args[3]
            if len(args) > 4:
                sequence_frames = args[4]
        else:
            # Alternate positional: (doc_img, live_img, [seq])
            doc_img = args[0]
            if len(args) > 1:
                live_img = args[1]
            if len(args) > 2:
                sequence_frames = args[2]

    if not verification_id:
        verification_id = f"vid-{uuid.uuid4()}"

    return face_verification_service.verify(
        verification_id=verification_id,
        document_image_bytes=doc_img,
        live_frame_bytes=live_img,
        sequence_frame_bytes=sequence_frames,
        document_type=document_type,
        portrait_region=portrait_region,
        document_profile=document_profile,
        client_metadata=client_metadata,
    )
