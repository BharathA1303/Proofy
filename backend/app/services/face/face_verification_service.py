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
from typing import List, Optional

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
from app.services.face.face_detector import FaceDetector, face_detector
from app.services.face.face_enhancer import DocumentFaceEnhancer
from app.services.face.face_matcher import compare_face_embeddings
from app.services.face.face_quality import FaceQualityResult, evaluate_face_quality
from app.services.face.minifasnet_pad import MiniFASNetPAD
from app.services.face.secondary_pad import SecondaryOpticalPAD
from app.services.face.session_store import session_document_store

logger = logging.getLogger(__name__)


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
        document_image_bytes: bytes,
        live_frame_bytes: bytes,
        sequence_frame_bytes: Optional[List[bytes]] = None,
        document_type: str = "passport",
    ) -> FaceVerificationResponse:
        """
        Execute the end-to-end biometric verification workflow.
        """
        t0 = time.time()
        logger.info(
            "Starting biometric verification (session=%s, doc_type=%s, burst_frames=%d)",
            verification_id,
            document_type,
            len(sequence_frame_bytes) if sequence_frame_bytes else 0,
        )

        # ── 1. Image Decoding ─────────────────────────────────────────
        if isinstance(document_image_bytes, np.ndarray):
            doc_img = document_image_bytes
        else:
            doc_img = cv2.imdecode(np.frombuffer(document_image_bytes, np.uint8), cv2.IMREAD_COLOR)

        if isinstance(live_frame_bytes, np.ndarray):
            live_img = live_frame_bytes
        else:
            live_img = cv2.imdecode(np.frombuffer(live_frame_bytes, np.uint8), cv2.IMREAD_COLOR)

        if doc_img is None or live_img is None:
            logger.error("Failed to decode document or live frame bytes.")
            return self._build_error_response(
                verification_id=verification_id,
                document_type=document_type,
                status="failed",
                overall="PROCESSING_ERROR",
                summary="Failed to decode biometric image payloads.",
            )

        # ── 2. Document Face Localization & Fast-Path Cache ───────────
        cached_face = session_document_store.get_face_cache(verification_id)
        doc_aligned = None
        doc_embedding = None

        if cached_face is not None:
            doc_box = cached_face["doc_box"]
            doc_crop = cached_face["doc_crop"]
            doc_aligned = cached_face.get("doc_aligned")
            doc_embedding = cached_face.get("doc_embedding")
            doc_detector_used = cached_face.get("detector_used", "InsightFace-SCRFD-10G")
            doc_quality = evaluate_face_quality(doc_crop, is_document=True)
            logger.info("Fast-path: Reused cached document face for session=%s", verification_id)
        else:
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
        live_crop = self.detector.crop_face(live_img, live_box)
        live_quality = evaluate_face_quality(live_crop, is_document=False)

        # ── 4. Decode Sequence Frames for Temporal PAD ────────────────
        sequence_items = []
        sequence_crops = []
        if sequence_frame_bytes:
            for b in sequence_frame_bytes:
                if isinstance(b, np.ndarray):
                    s_img = b
                else:
                    s_img = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
                if s_img is not None:
                    # Fast sequence crop reusing anchor live_box (avoids 400ms SCRFD re-detection per frame)
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
                verification_id,
                document_type,
                doc_quality,
                live_quality,
                doc_detector_used,
                live_detect.detector_used,
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
                verification_id, document_type, doc_quality, live_quality, pad_result, secondary_pad_res
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

        # ── 9. Cosine Similarity Matching ─────────────────────────────
        match_result = compare_face_embeddings(
            doc_embedding,
            live_embedding,
            threshold=settings.FACE_MATCH_THRESHOLD,
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

        elapsed_ms = (time.time() - t0) * 1000.0
        logger.info(
            "Biometric verification completed in %.1fms (status=%s, match=%s, pad=%s)",
            elapsed_ms,
            overall_status,
            match_result.status,
            pad_result.status,
        )

        return FaceVerificationResponse(
            verification_id=verification_id,
            document_type=document_type,
            status="completed",
            overall_assessment=overall_status,
            overall_biometric_status=overall_status,
            document_face=self._to_doc_face_result(doc_quality, doc_detector_used),
            live_face=self._to_live_face_result(live_quality, live_detect.detector_used),
            anti_spoof=AntiSpoofResult(
                model=pad_result.model_name,
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
                status=match_result.status,
                similarity=match_result.similarity,
                similarity_score=match_result.confidence_score if match_result.confidence_score is not None else match_result.similarity,
                threshold=match_result.threshold,
                embedding_model=self.embedding_model.model_info().get("model_name", "ArcFace-w600k_r50"),
                embedding_dimension=self.embedding_model.get_embedding_dimension(),
                explanation=match_result.explanation,
            ),
            document_face_image=_crop_to_b64(doc_crop),
            live_face_image=_crop_to_b64(live_crop),
            summary=summary,
        )

    # ── Helpers for Non-Nominal Response Scenarios ─────────────────────

    def _build_document_face_missing_response(
        self, verification_id: str, document_type: str, detector_name: str
    ) -> FaceVerificationResponse:
        if document_type.lower() == "visa":
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
                    status="inconclusive", score=None, explanation="Biometrics not applicable for this Visa profile."
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
                    explanation="No usable portrait region was identified for this Visa profile.",
                ),
                summary="Biometric verification not applicable: No usable portrait region was identified for this Visa profile.",
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
    ) -> FaceVerificationResponse:
        reasons = []
        if not doc_q.is_acceptable:
            reasons.append(f"document face quality poor ({doc_q.explanation})")
        if not live_q.is_acceptable:
            reasons.append(f"live capture quality poor ({live_q.explanation})")
        msg = "Biometric quality gate failed: " + "; ".join(reasons)

        return FaceVerificationResponse(
            verification_id=verification_id,
            document_type=document_type,
            status="failed",
            overall_assessment="POOR_QUALITY",
            overall_biometric_status="POOR_QUALITY",
            document_face=self._to_doc_face_result(doc_q, doc_det),
            live_face=self._to_live_face_result(live_q, live_det),
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
    ) -> FaceVerificationResponse:
        return FaceVerificationResponse(
            verification_id=verification_id,
            document_type=document_type,
            status="model_unavailable",
            overall_assessment="MODEL_UNAVAILABLE",
            overall_biometric_status="BIOMETRIC_INCONCLUSIVE",
            document_face=self._to_doc_face_result(doc_q, "InsightFace-SCRFD"),
            live_face=self._to_live_face_result(live_q, "InsightFace-SCRFD"),
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
    def _to_doc_face_result(q: FaceQualityResult, det_name: str) -> DocumentFaceResult:
        detail = FaceQualityDetail(
            status=q.status,
            blur=q.blur,
            brightness=q.brightness,
            contrast=q.contrast,
            face_size=q.face_size,
            pose=q.pose,
            explanation=q.explanation,
        )
        return DocumentFaceResult(
            detected=True,
            face_count=1,
            quality=q.status,
            quality_details=detail,
            detector_used=det_name,
            error=q.error_code,
        )

    @staticmethod
    def _to_live_face_result(q: FaceQualityResult, det_name: str) -> LiveFaceResult:
        detail = FaceQualityDetail(
            status=q.status,
            blur=q.blur,
            brightness=q.brightness,
            contrast=q.contrast,
            face_size=q.face_size,
            pose=q.pose,
            explanation=q.explanation,
        )
        return LiveFaceResult(
            detected=True,
            face_count=1,
            quality=q.status,
            quality_details=detail,
            detector_used=det_name,
            error=q.error_code,
        )


face_verification_service = FaceVerificationService()


def verify_passport_biometrics(
    verification_id: str,
    document_type: str,
    document_image_bgr: np.ndarray,
    live_frame_bgr: np.ndarray,
    sequence_frames_bgr: Optional[List[np.ndarray]] = None,
) -> FaceVerificationResponse:
    """
    Convenience function for Module 4 verification using decoded NumPy arrays.
    """
    return face_verification_service.verify(
        verification_id=verification_id,
        document_image_bytes=document_image_bgr,
        live_frame_bytes=live_frame_bgr,
        sequence_frame_bytes=sequence_frames_bgr,
        document_type=document_type,
    )
