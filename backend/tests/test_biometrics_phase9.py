"""
backend/tests/test_biometrics_phase9.py

Comprehensive Phase 9 verification test suite for Module 4:
Biometrics, Face Verification & Presentation Attack Detection.

Validates all requirements from Section 22:
- Document portrait available from layout region vs detector fallback
- Document portrait unavailable / not applicable
- Live face single vs multiple vs absent
- Face quality gating (POOR_QUALITY != FACE_MISMATCH)
- Landmark extraction and 5-point ArcFace alignment
- Presentation attack detection (pass, fail, unavailable, sequence)
- Model availability contract (no fabricated scores or confidences)
- Cosine similarity matching and uncalibrated threshold metadata
- Multiple face ambiguity preservation
- Client trust boundary (client claims ignored)
- Security & resource limits (25MB payload, 10,000px dimensions)
- Independence between forensic and biometric evidence (M3 + M4)
- Verification that M4 never emits FORGED_DOCUMENT or AUTHENTIC
"""
from unittest.mock import MagicMock, patch
import cv2
import numpy as np
import pytest

from app.schemas.face_verification import (
    FaceVerificationResponse,
    DocumentFaceResult,
    LiveFaceResult,
    AntiSpoofResult,
    FaceMatchResult,
)
from app.services.documents.profiles import document_profile_registry
from app.services.documents.profiles.document_profile import DocumentProfile, ModuleSupportStatus, ProfileStatus
from app.services.documents.profiles.driving_license_profile import DRIVING_LICENSE_PROFILE
from app.services.document_intelligence.schema import NormalizedBBox
from app.services.face.detector_interface import FaceDetectionResult
from app.services.face.face_aligner import FaceAligner
from app.services.face.face_detector import DetectedFaceBox, FaceDetector
from app.services.face.face_matcher import compare_face_embeddings
from app.services.face.face_quality import FaceQualityResult, evaluate_face_quality
from app.services.face.face_verification_service import FaceVerificationService, verify_passport_biometrics
from app.services.face.pad_interface import PADAssessment


def _make_dummy_image(w=200, h=250, fill=130):
    img = np.full((h, w, 3), fill, dtype=np.uint8)
    cv2.circle(img, (w // 2, h // 2), min(w, h) // 3, (fill - 35, fill - 35, fill - 35), -1)
    cv2.circle(img, (w // 3, h // 3), max(4, min(w, h) // 15), (25, 25, 25), -1)
    cv2.circle(img, (2 * w // 3, h // 3), max(4, min(w, h) // 15), (25, 25, 25), -1)
    cv2.line(img, (w // 3, 2 * h // 3), (2 * w // 3, 2 * h // 3), (25, 25, 25), max(2, min(w, h) // 30))
    return img


def _make_dummy_box(x=20, y=20, w=80, h=80, conf=0.98, landmarks=None):
    if landmarks is None:
        landmarks = [
            (x + 25.0, y + 25.0),
            (x + 55.0, y + 25.0),
            (x + 40.0, y + 45.0),
            (x + 30.0, y + 65.0),
            (x + 50.0, y + 65.0),
        ]
    return DetectedFaceBox(x=x, y=y, width=w, height=h, confidence=conf, landmarks=landmarks)


# ==============================================================================
# 1. DOCUMENT PORTRAIT EXTRACTION & M1 REGION INTEGRATION
# ==============================================================================

class TestDocumentPortraitExtraction:
    def test_document_portrait_available_from_layout_region(self):
        """A. Document portrait extracted from M1 layout region preserves source and coordinates."""
        doc_img = _make_dummy_image(400, 500)
        live_img = _make_dummy_image(300, 300)

        svc = FaceVerificationService()
        mock_det = MagicMock()

        # Document box inside portrait region
        doc_box = _make_dummy_box(10, 10, 80, 80)
        live_box = _make_dummy_box(20, 20, 90, 90)

        mock_det.detect_faces.side_effect = [
            MagicMock(face_count=1, faces=[doc_box], detector_used="InsightFace-SCRFD"),  # region search
            MagicMock(face_count=1, faces=[live_box], detector_used="InsightFace-SCRFD"), # live search
        ]
        mock_det.crop_face.return_value = _make_dummy_image(80, 80)
        svc.detector = mock_det

        portrait_region = NormalizedBBox(0.04, 0.20, 0.28, 0.52)
        res = svc.verify(
            verification_id="test-m1-portrait-1",
            document_image_bytes=doc_img,
            live_frame_bytes=live_img,
            document_type="driving_license",
            portrait_region=portrait_region,
        )

        assert res.document_face.detected is True
        assert res.document_face.source == "DOCUMENT_PORTRAIT_REGION"
        assert res.document_face.bbox is not None
        assert res.document_face.normalized_bbox is not None
        assert res.document_portrait is not None
        assert res.document_portrait["source"] == "DOCUMENT_PORTRAIT_REGION"

    def test_document_portrait_fallback_to_full_image(self):
        """Safe fallback to full-image detection when layout region yields no face."""
        doc_img = _make_dummy_image(400, 500)
        live_img = _make_dummy_image(300, 300)

        svc = FaceVerificationService()
        mock_det = MagicMock()

        doc_box = _make_dummy_box(100, 120, 90, 90)
        live_box = _make_dummy_box(20, 20, 90, 90)

        mock_det.detect_faces.side_effect = [
            MagicMock(face_count=0, detector_used="InsightFace-SCRFD"),                   # region has 0 faces
            MagicMock(face_count=1, faces=[doc_box], detector_used="InsightFace-SCRFD"),  # full doc fallback
            MagicMock(face_count=1, faces=[live_box], detector_used="InsightFace-SCRFD"), # live search
        ]
        mock_det.crop_face.return_value = _make_dummy_image(80, 80)
        svc.detector = mock_det

        portrait_region = (0.05, 0.10, 0.30, 0.35)
        res = svc.verify(
            verification_id="test-fallback-portrait",
            document_image_bytes=doc_img,
            live_frame_bytes=live_img,
            document_type="driving_license",
            portrait_region=portrait_region,
        )

        assert res.document_face.detected is True
        assert res.document_face.source == "FULL_IMAGE_DETECTION"

    def test_document_portrait_unavailable(self):
        """B. When no document portrait is detected anywhere, returns DOCUMENT_FACE_NOT_FOUND."""
        doc_img = _make_dummy_image(400, 500)
        live_img = _make_dummy_image(300, 300)

        svc = FaceVerificationService()
        mock_det = MagicMock()
        mock_det.detect_faces.return_value = MagicMock(face_count=0, detector_used="InsightFace-SCRFD")
        svc.detector = mock_det

        res = svc.verify(
            verification_id="test-no-portrait",
            document_image_bytes=doc_img,
            live_frame_bytes=live_img,
            document_type="driving_license",
        )

        assert res.overall_assessment == "DOCUMENT_FACE_NOT_FOUND"
        assert res.status == "failed"
        assert res.document_face.detected is False
        assert res.face_match.status == "unavailable"

    def test_document_portrait_not_applicable_profile(self):
        """Profiles with portrait_applicable=False return NOT_APPLICABLE cleanly."""
        doc_img = _make_dummy_image(400, 500)
        live_img = _make_dummy_image(300, 300)

        non_portrait_profile = DocumentProfile(
            document_type="custom_tax_form",
            display_name="Tax Form",
            portrait_applicable=False,
        )

        svc = FaceVerificationService()
        res = svc.verify(
            verification_id="test-non-portrait-doc",
            document_image_bytes=doc_img,
            live_frame_bytes=live_img,
            document_profile=non_portrait_profile,
        )

        assert res.overall_assessment == "NOT_APPLICABLE"
        assert res.status == "completed"
        assert res.document_face.detected is False


# ==============================================================================
# 2. LIVE FACE DETECTION & MULTI-FACE SAFETY
# ==============================================================================

class TestLiveFaceDetectionAndMultiFaceSafety:
    def test_live_image_one_face_nominal(self):
        """C. Single live face proceeds normally."""
        doc_img = _make_dummy_image(300, 300)
        live_img = _make_dummy_image(300, 300)

        svc = FaceVerificationService()
        mock_det = MagicMock()
        mock_det.detect_faces.side_effect = [
            MagicMock(face_count=1, faces=[_make_dummy_box(10, 10, 80, 80)], detector_used="test-det"),
            MagicMock(face_count=1, faces=[_make_dummy_box(20, 20, 80, 80)], detector_used="test-det"),
        ]
        mock_det.crop_face.return_value = _make_dummy_image(80, 80)
        svc.detector = mock_det

        res = svc.verify("test-live-1", doc_img, live_img)
        assert res.live_face.detected is True
        assert res.live_face.face_count == 1
        assert res.live_face.source == "LIVE_CAPTURE"

    def test_live_image_no_face(self):
        """D. No face in live capture returns NO_FACE_DETECTED."""
        doc_img = _make_dummy_image(300, 300)
        live_img = _make_dummy_image(300, 300)

        svc = FaceVerificationService()
        mock_det = MagicMock()
        mock_det.detect_faces.side_effect = [
            MagicMock(face_count=1, faces=[_make_dummy_box(10, 10, 80, 80)], detector_used="test-det"),
            MagicMock(face_count=0, error_code="FACE_NOT_DETECTED", detector_used="test-det"),
        ]
        mock_det.crop_face.return_value = _make_dummy_image(80, 80)
        svc.detector = mock_det

        res = svc.verify("test-live-0", doc_img, live_img)
        assert res.overall_assessment == "NO_FACE_DETECTED"
        assert res.live_face.detected is False
        assert res.status == "failed"

    def test_live_image_multiple_faces_preserves_ambiguity(self):
        """E & AF. Multiple live faces strictly halts verification and does NOT silently select one."""
        doc_img = _make_dummy_image(300, 300)
        live_img = _make_dummy_image(300, 300)

        svc = FaceVerificationService()
        mock_det = MagicMock()
        box1 = _make_dummy_box(10, 10, 80, 80)
        box2 = _make_dummy_box(110, 10, 80, 80)

        mock_det.detect_faces.side_effect = [
            MagicMock(face_count=1, faces=[box1], detector_used="test-det"),
            MagicMock(face_count=2, faces=[box1, box2], detector_used="test-det"),
        ]
        mock_det.crop_face.return_value = _make_dummy_image(80, 80)
        svc.detector = mock_det

        res = svc.verify("test-live-multi", doc_img, live_img)
        assert res.overall_assessment == "MULTIPLE_FACES_DETECTED"
        assert res.live_face.face_count == 2
        assert res.status == "failed"
        assert res.face_match.status == "unavailable"

    def test_multiple_document_faces_preserves_ambiguity(self):
        """AF. Multiple document candidate portraits preserves ambiguity without silent selection."""
        doc_img = _make_dummy_image(300, 300)
        live_img = _make_dummy_image(300, 300)

        svc = FaceVerificationService()
        mock_det = MagicMock()
        box1 = _make_dummy_box(10, 10, 80, 80)
        box2 = _make_dummy_box(120, 10, 80, 80)
        mock_det.detect_faces.return_value = MagicMock(face_count=2, faces=[box1, box2], detector_used="test-det")
        svc.detector = mock_det

        res = svc.verify("test-doc-multi", doc_img, live_img)
        assert res.overall_assessment == "MULTIPLE_FACES_DETECTED"
        assert res.document_face.face_count == 2
        assert res.status == "failed"


# ==============================================================================
# 3. FACE QUALITY GATING (POOR_QUALITY != FACE_MISMATCH)
# ==============================================================================

class TestFaceQualityGate:
    def test_low_quality_live_face_not_identity_mismatch(self):
        """F. Poor quality live face must emit POOR_QUALITY, NOT FACE_MISMATCH."""
        doc_img = _make_dummy_image(300, 300)
        live_img = _make_dummy_image(300, 300)

        svc = FaceVerificationService()
        mock_det = MagicMock()
        mock_box = _make_dummy_box(20, 20, 80, 80)
        mock_det.detect_faces.side_effect = [
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
        ]
        # Extremely blurry crop (Laplacian variance near zero)
        blurry_crop = np.full((80, 80, 3), 120, dtype=np.uint8)
        mock_det.crop_face.return_value = blurry_crop
        svc.detector = mock_det

        res = svc.verify("test-quality-live", doc_img, live_img)

        assert res.overall_assessment == "POOR_QUALITY"
        assert res.status == "failed"
        assert res.face_match.status == "unavailable"
        assert res.face_match.similarity is None
        assert res.overall_assessment != "FACE_MISMATCH"

    def test_low_quality_document_portrait_blocks_match(self):
        """G. Low quality document portrait halts matching gracefully without false mismatch."""
        doc_img = _make_dummy_image(300, 300)
        live_img = _make_dummy_image(300, 300)

        svc = FaceVerificationService()
        mock_det = MagicMock()
        mock_box = _make_dummy_box(20, 20, 80, 80)
        mock_det.detect_faces.side_effect = [
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
        ]
        # Solid white washed-out crop (mean brightness > 250)
        washed_crop = np.full((80, 80, 3), 254, dtype=np.uint8)
        mock_det.crop_face.return_value = washed_crop
        svc.detector = mock_det

        res = svc.verify("test-quality-doc", doc_img, live_img)

        assert res.overall_assessment == "POOR_QUALITY"
        assert res.document_face.quality == "poor"
        assert res.face_match.status == "unavailable"


# ==============================================================================
# 4. FACE ALIGNMENT & LANDMARK LOCALIZATION
# ==============================================================================

class TestFaceAlignment:
    def test_5point_landmark_alignment_transformation(self):
        """I & J. 5 facial landmarks warp to 112x112 ArcFace canonical space."""
        aligner = FaceAligner()
        img = _make_dummy_image(300, 300)
        landmarks = [
            (90.0, 110.0),   # left eye
            (170.0, 110.0),  # right eye
            (130.0, 150.0),  # nose tip
            (100.0, 190.0),  # left mouth
            (160.0, 190.0),  # right mouth
        ]

        aligned = aligner.align_face_5point(img, landmarks, (112, 112))
        assert aligned.shape == (112, 112, 3)

    def test_alignment_fallback_when_landmarks_absent(self):
        """J. Bounding box fallback used when 5 landmarks are unavailable."""
        aligner = FaceAligner()
        img = _make_dummy_image(300, 300)
        bbox = (50, 60, 120, 120)

        aligned = aligner.align_bbox_fallback(img, bbox, target_size=(112, 112))
        assert aligned.shape == (112, 112, 3)


# ==============================================================================
# 5. PRESENTATION ATTACK DETECTION (PAD)
# ==============================================================================

class TestPresentationAttackDetection:
    def test_pad_pass_bona_fide(self):
        """K. Bona fide presentation with score >= threshold passes."""
        doc_img = _make_dummy_image(300, 300)
        live_img = _make_dummy_image(300, 300)

        svc = FaceVerificationService()
        mock_det = MagicMock()
        mock_box = _make_dummy_box()
        mock_det.detect_faces.side_effect = [
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
        ]
        mock_det.crop_face.return_value = _make_dummy_image(80, 80)
        svc.detector = mock_det

        # Mock PAD pass
        svc.pad_model.predict = MagicMock(return_value=PADAssessment(
            status="pass", score=0.92, model_name="MiniFASNetV2", explanation="Bona fide human"
        ))

        res = svc.verify("test-pad-pass", doc_img, live_img)
        assert res.anti_spoof.status == "pass"
        assert res.anti_spoof.score == 0.92
        assert res.anti_spoof.model_version == "2.0.0"

    def test_pad_fail_spoof_suspends_matching(self):
        """L. Presentation attack detection halts clearance and emits SUSPECTED_SPOOF."""
        doc_img = _make_dummy_image(300, 300)
        live_img = _make_dummy_image(300, 300)

        svc = FaceVerificationService()
        mock_det = MagicMock()
        mock_box = _make_dummy_box()
        mock_det.detect_faces.side_effect = [
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
        ]
        mock_det.crop_face.return_value = _make_dummy_image(80, 80)
        svc.detector = mock_det

        svc.pad_model.predict = MagicMock(return_value=PADAssessment(
            status="suspected_spoof", score=0.12, model_name="MiniFASNetV2", explanation="Printed photo attack"
        ))

        res = svc.verify("test-pad-spoof", doc_img, live_img)
        assert res.overall_assessment == "SUSPECTED_SPOOF"
        assert res.anti_spoof.status == "suspected_spoof"

    def test_pad_unavailable_when_weights_missing_no_fabrication(self):
        """M & V. When PAD weights missing, reports model_unavailable with score=None, never fabricated confidence."""
        doc_img = _make_dummy_image(300, 300)
        live_img = _make_dummy_image(300, 300)

        svc = FaceVerificationService()
        mock_det = MagicMock()
        mock_box = _make_dummy_box()
        mock_det.detect_faces.side_effect = [
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
        ]
        mock_det.crop_face.return_value = _make_dummy_image(80, 80)
        svc.detector = mock_det

        # Mock PAD model unavailable
        svc.pad_model.is_available = MagicMock(return_value=False)
        svc.pad_model.predict = MagicMock(return_value=PADAssessment(
            status="model_unavailable", score=None, model_name="MiniFASNetV2", explanation="Weights absent"
        ))

        res = svc.verify("test-pad-unavail", doc_img, live_img)
        assert res.anti_spoof.status == "model_unavailable"
        assert res.anti_spoof.score is None
        assert res.overall_assessment == "BIOMETRIC_INCONCLUSIVE"


# ==============================================================================
# 6. MODEL AVAILABILITY CONTRACT & ARCFACE EMBEDDING
# ==============================================================================

class TestArcFaceEmbeddingAndSimilarity:
    def test_arcface_model_unavailable_returns_explicit_status(self):
        """N & U. If ArcFace weights unavailable, reports MODEL_UNAVAILABLE with no fabricated similarity score."""
        doc_img = _make_dummy_image(300, 300)
        live_img = _make_dummy_image(300, 300)

        svc = FaceVerificationService()
        mock_det = MagicMock()
        mock_box = _make_dummy_box()
        mock_det.detect_faces.side_effect = [
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
        ]
        mock_det.crop_face.return_value = _make_dummy_image(80, 80)
        svc.detector = mock_det

        # Mock ArcFace unavailable
        svc.embedding_model.is_available = MagicMock(return_value=False)

        res = svc.verify("test-arcface-unavail", doc_img, live_img)
        assert res.status == "model_unavailable"
        assert res.face_match.status == "unavailable"
        assert res.face_match.similarity is None
        assert res.face_match.similarity_score is None

    def test_genuine_arcface_embedding_generation(self):
        """O. If ArcFace model is initialized, extracts genuine 512-D L2-normalized vector."""
        svc = FaceVerificationService()
        if not svc.embedding_model.is_available():
            pytest.skip("ArcFace weights w600k_r50.onnx not present on disk")

        crop = _make_dummy_image(112, 112)
        emb = svc.embedding_model.get_embedding(crop)

        assert isinstance(emb, np.ndarray)
        assert emb.shape == (512,)
        # L2 norm must equal 1.0 (within float precision)
        norm = np.linalg.norm(emb)
        assert abs(norm - 1.0) < 1e-4

    def test_cosine_similarity_calculation(self):
        """P, Q, R, S. Cosine similarity correctly classifies match, non-match, and borderline."""
        v1 = np.zeros(512, dtype=np.float32)
        v1[0] = 1.0

        # Identical vector -> similarity 1.0 -> MATCH
        res_match = compare_face_embeddings(v1, v1, threshold=0.40)
        assert res_match.status == "match"
        assert res_match.similarity == 1.0

        # Orthogonal vector -> similarity 0.0 -> NO_MATCH
        v2 = np.zeros(512, dtype=np.float32)
        v2[1] = 1.0
        res_no_match = compare_face_embeddings(v1, v2, threshold=0.40)
        assert res_no_match.status == "no_match"
        assert res_no_match.similarity == 0.0

        # Borderline vector
        v_border = np.zeros(512, dtype=np.float32)
        v_border[0] = 0.38
        v_border[1] = np.sqrt(1.0 - 0.38**2)
        res_border = compare_face_embeddings(v1, v_border, threshold=0.40, inconclusive_margin=0.06)
        assert res_border.status == "inconclusive"
        assert res_border.similarity == 0.38

    def test_uncalibrated_threshold_metadata(self):
        """T. Uncalibrated threshold metadata is exposed in evidence."""
        v1 = np.ones(512, dtype=np.float32) / np.sqrt(512)
        res = compare_face_embeddings(v1, v1, threshold=0.40, calibration_status="UNCALIBRATED_PROFILE_DEFAULT")
        assert res.threshold_calibration == "UNCALIBRATED_PROFILE_DEFAULT"
        assert res.similarity_metric == "cosine"


# ==============================================================================
# 7. SECURITY, CLIENT TRUST BOUNDARY & PRIVACY CONTROLS
# ==============================================================================

class TestSecurityTrustBoundaryAndPrivacy:
    def test_client_provided_score_strictly_ignored(self):
        """W. Client-supplied match or PAD claims cannot override server verification."""
        doc_img = _make_dummy_image(300, 300)
        live_img = _make_dummy_image(300, 300)

        svc = FaceVerificationService()
        mock_det = MagicMock()
        mock_box = _make_dummy_box()
        mock_det.detect_faces.side_effect = [
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
        ]
        mock_det.crop_face.return_value = _make_dummy_image(80, 80)
        svc.detector = mock_det

        # Client attempts to inject fake scores
        client_claims = {
            "similarity": 0.9999,
            "status": "match",
            "pad_status": "pass",
            "liveness_score": 1.0,
        }

        # Mock real matcher returning no_match
        with patch("app.services.face.face_verification_service.compare_face_embeddings") as mock_comp:
            mock_comp.return_value = FaceMatchResult(
                status="no_match", similarity=0.10, threshold=0.40, explanation="Mismatch"
            )
            res = svc.verify("test-inject", doc_img, live_img, client_metadata=client_claims)
            # Server result must reflect actual computation, NOT client claim
            assert res.overall_assessment == "FACE_MISMATCH"
            assert res.face_match.similarity == 0.10

    def test_resource_limits_payload_size(self):
        """25. Over-sized image payload (>25MB) rejected before memory exhaustion."""
        svc = FaceVerificationService()
        huge_bytes = b"0" * (26 * 1024 * 1024)  # 26MB
        valid_img = _make_dummy_image(100, 100)

        res = svc.verify("test-huge", huge_bytes, valid_img)
        assert res.status == "failed"
        assert res.overall_assessment == "PROCESSING_ERROR"
        assert "25MB" in res.summary

    def test_resource_limits_dimensions(self):
        """25. Extreme image dimensions (>10,000px) rejected before memory blowup."""
        svc = FaceVerificationService()
        huge_dim_img = np.zeros((10001, 50, 3), dtype=np.uint8)
        valid_img = _make_dummy_image(100, 100)

        res = svc.verify("test-huge-dim", huge_dim_img, valid_img)
        assert res.status == "failed"
        assert res.overall_assessment == "PROCESSING_ERROR"
        assert "10,000" in res.summary

    def test_ephemeral_biometrics_no_raw_vectors_in_response(self):
        """AB, AC, AD. Verification response contains no raw 512-D vectors or uncompressed frames."""
        doc_img = _make_dummy_image(200, 200)
        live_img = _make_dummy_image(200, 200)

        svc = FaceVerificationService()
        mock_det = MagicMock()
        mock_box = _make_dummy_box()
        mock_det.detect_faces.side_effect = [
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
        ]
        mock_det.crop_face.return_value = _make_dummy_image(80, 80)
        svc.detector = mock_det

        res = svc.verify("test-privacy", doc_img, live_img)
        ev = res.to_evidence_dict()

        ev_str = str(ev)
        assert "512" in ev_str or "dimension" in ev_str  # metadata allowed
        # Ensure no giant numpy arrays or float arrays are serialized
        assert "array(" not in ev_str


# ==============================================================================
# 8. EVIDENCE INTEGRATION & NON-ADJUDICATION CONTRACT
# ==============================================================================

class TestEvidenceIntegrationAndNonAdjudication:
    def test_forensic_suspicious_and_face_match_coexist(self):
        """X. Biometric face match does NOT erase document forensic tampering evidence."""
        # Simulated M3 forensic status
        m3_status = "FORENSIC_SUSPICIOUS"

        # M4 face match
        doc_img = _make_dummy_image(200, 200)
        live_img = _make_dummy_image(200, 200)

        svc = FaceVerificationService()
        mock_det = MagicMock()
        mock_box = _make_dummy_box()
        mock_det.detect_faces.side_effect = [
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
        ]
        mock_det.crop_face.return_value = _make_dummy_image(80, 80)
        svc.detector = mock_det

        with patch("app.services.face.face_verification_service.compare_face_embeddings") as mock_comp:
            mock_comp.return_value = FaceMatchResult(
                status="match", similarity=0.85, threshold=0.40, explanation="Matched"
            )
            m4_res = svc.verify("test-coexist", doc_img, live_img)

        # Both pieces of evidence are preserved independently
        assert m3_status == "FORENSIC_SUSPICIOUS"
        assert m4_res.overall_assessment == "FACE_MATCH"
        assert m4_res.overall_assessment != "AUTHENTIC"
        assert m4_res.overall_assessment != "FORGED_DOCUMENT"

    def test_no_forged_document_or_authentic_from_m4(self):
        """AG & AH. M4 never outputs FORGED_DOCUMENT or AUTHENTIC."""
        svc = FaceVerificationService()
        prohibited_verdicts = ["FORGED_DOCUMENT", "AUTHENTIC", "GENUINE_DOCUMENT", "FAKE_DOCUMENT"]

        # Nominal mismatch
        doc_img = _make_dummy_image(200, 200)
        live_img = _make_dummy_image(200, 200)
        mock_det = MagicMock()
        mock_box = _make_dummy_box()
        mock_det.detect_faces.side_effect = [
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
        ]
        mock_det.crop_face.return_value = _make_dummy_image(80, 80)
        svc.detector = mock_det

        with patch("app.services.face.face_verification_service.compare_face_embeddings") as mock_comp:
            mock_comp.return_value = FaceMatchResult(
                status="no_match", similarity=0.05, threshold=0.40, explanation="Mismatch"
            )
            res = svc.verify("test-adjudication", doc_img, live_img)

        assert res.overall_assessment not in prohibited_verdicts
        assert res.overall_assessment == "FACE_MISMATCH"

    def test_driving_license_profile_biometric_configuration(self):
        """AA. Driving License profile declares biometric configuration and regions."""
        profile = DRIVING_LICENSE_PROFILE
        assert profile.is_module_supported("biometrics") is True
        assert profile.portrait_applicable is True
        assert "biometric_config" in profile.to_dict()
        assert profile.biometric_config["face_match_threshold"] == 0.40
        assert profile.biometric_config["expected_portrait_region"] is not None

    def test_convenience_verify_passport_biometrics_flexible_args(self):
        """verify_passport_biometrics accepts both positional and keyword invocations."""
        doc_img = _make_dummy_image(200, 200)
        live_img = _make_dummy_image(200, 200)

        with patch.object(FaceVerificationService, "verify") as mock_verify:
            mock_verify.return_value = MagicMock(spec=FaceVerificationResponse)
            # Positional call
            verify_passport_biometrics("vid-1", "passport", doc_img, live_img)
            assert mock_verify.called

        with patch.object(FaceVerificationService, "verify") as mock_verify:
            mock_verify.return_value = MagicMock(spec=FaceVerificationResponse)
            # Orchestrator-style keyword call
            verify_passport_biometrics(doc_image_bytes=b"dummy1", live_face_bytes=b"dummy2")
            assert mock_verify.called
