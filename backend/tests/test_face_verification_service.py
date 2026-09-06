"""
backend/tests/test_face_verification_service.py

Comprehensive tests for FaceVerificationService and biometric orchestrator logic.
Tests all nominal and edge-case branching according to the Phase 4 decision matrix.
"""
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from app.schemas.face_verification import FaceVerificationResponse
from app.services.face.detector_interface import FaceDetectionResult, FaceDetector
from app.services.face.face_detector import DetectedFaceBox
from app.services.face.face_quality import FaceQualityResult
from app.services.face.face_verification_service import FaceVerificationService, verify_passport_biometrics
from app.services.face.pad_interface import PADAssessment


def _dummy_image(w=200, h=250):
    return np.full((h, w, 3), 128, dtype=np.uint8)


class TestFaceVerificationService:
    def test_no_document_face_detected(self):
        doc_img = _dummy_image()
        live_img = _dummy_image()

        svc = FaceVerificationService()
        mock_det = MagicMock()
        # Doc returns 0 faces
        mock_det.detect_faces.return_value = MagicMock(face_count=0, detector_used="test-det")
        svc.detector = mock_det

        res = svc.verify("test-id-1", doc_img, live_img)

        assert res.overall_assessment == "DOCUMENT_FACE_NOT_FOUND"
        assert res.overall_biometric_status == "DOCUMENT_FACE_NOT_FOUND"
        assert res.status == "failed"
        assert res.document_face.detected is False
        assert res.document_face.error == "DOCUMENT_FACE_NOT_FOUND"
        assert res.face_match.status == "unavailable"

    def test_multiple_document_faces_detected(self):
        doc_img = _dummy_image()
        live_img = _dummy_image()

        svc = FaceVerificationService()
        mock_det = MagicMock()
        mock_det.detect_faces.return_value = MagicMock(face_count=2, detector_used="test-det")
        svc.detector = mock_det

        res = svc.verify("test-id-2", doc_img, live_img)

        assert res.overall_assessment == "MULTIPLE_FACES_DETECTED"
        assert res.overall_biometric_status == "MULTIPLE_FACES_DETECTED"
        assert res.document_face.error == "MULTIPLE_FACES_DETECTED"
        assert res.document_face.face_count == 2
        assert res.status == "failed"

    def test_no_live_face_detected(self):
        doc_img = _dummy_image()
        live_img = _dummy_image()

        svc = FaceVerificationService()
        mock_det = MagicMock()
        mock_box = DetectedFaceBox(10, 10, 80, 80)
        # Doc returns 1 face, live returns 0
        mock_det.detect_faces.side_effect = [
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
            MagicMock(face_count=0, detector_used="test-det"),
        ]
        mock_det.crop_face.return_value = _dummy_image(80, 80)
        svc.detector = mock_det

        res = svc.verify("test-id-3", doc_img, live_img)

        assert res.overall_assessment == "NO_FACE_DETECTED"
        assert res.overall_biometric_status == "NO_FACE_DETECTED"
        assert res.live_face.detected is False
        assert res.live_face.error == "FACE_NOT_DETECTED"
        assert res.status == "failed"

    def test_multiple_live_faces_detected(self):
        doc_img = _dummy_image()
        live_img = _dummy_image()

        svc = FaceVerificationService()
        mock_det = MagicMock()
        mock_box = DetectedFaceBox(10, 10, 80, 80)
        mock_det.detect_faces.side_effect = [
            MagicMock(face_count=1, faces=[mock_box], detector_used="test-det"),
            MagicMock(face_count=3, detector_used="test-det"),
        ]
        mock_det.crop_face.return_value = _dummy_image(80, 80)
        svc.detector = mock_det

        res = svc.verify("test-id-4", doc_img, live_img)

        assert res.overall_assessment == "MULTIPLE_FACES_DETECTED"
        assert res.overall_biometric_status == "MULTIPLE_FACES_DETECTED"
        assert res.live_face.face_count == 3
        assert res.status == "failed"

    def test_poor_document_face_quality_blocks_matching(self):
        doc_img = _dummy_image()
        live_img = _dummy_image()

        svc = FaceVerificationService()
        mock_det = MagicMock()
        mock_box = DetectedFaceBox(10, 10, 80, 80)
        mock_det.detect_faces.return_value = MagicMock(face_count=1, faces=[mock_box], detector_used="test-det")
        mock_det.crop_face.return_value = _dummy_image(80, 80)
        svc.detector = mock_det

        with patch("app.services.face.face_verification_service.evaluate_face_quality") as mock_qual:
            # Doc quality is poor (blurry)
            mock_qual.side_effect = [
                FaceQualityResult(
                    status="poor", blur="poor", brightness="acceptable", contrast="acceptable",
                    face_size="acceptable", pose="acceptable", blur_score=10.0, brightness_score=120.0,
                    contrast_score=30.0, width=80, height=80, error_code="FACE_TOO_BLURRY",
                    explanation="Face is too blurry.",
                ),
                FaceQualityResult(
                    status="acceptable", blur="acceptable", brightness="acceptable", contrast="acceptable",
                    face_size="acceptable", pose="acceptable", blur_score=80.0, brightness_score=120.0,
                    contrast_score=30.0, width=80, height=80,
                ),
            ]

            res = svc.verify("test-id-5", doc_img, live_img)

            assert res.overall_assessment == "POOR_QUALITY"
            assert res.overall_biometric_status == "POOR_QUALITY"
            assert res.document_face.quality == "poor"
            assert res.face_match.status == "unavailable"

    def test_suspected_spoof_overrides_similarity(self):
        doc_img = _dummy_image()
        live_img = _dummy_image()

        svc = FaceVerificationService()
        mock_det = MagicMock()
        mock_box = DetectedFaceBox(10, 10, 80, 80, landmarks=[(20, 25), (60, 25), (40, 45), (25, 65), (55, 65)])
        mock_det.detect_faces.return_value = MagicMock(face_count=1, faces=[mock_box], detector_used="test-det")
        mock_det.crop_face.return_value = _dummy_image(80, 80)
        svc.detector = mock_det

        with patch("app.services.face.face_verification_service.evaluate_face_quality") as mock_qual:
            mock_qual.return_value = FaceQualityResult(
                status="acceptable", blur="acceptable", brightness="acceptable", contrast="acceptable",
                face_size="acceptable", pose="acceptable", blur_score=80.0, brightness_score=120.0,
                contrast_score=30.0, width=80, height=80,
            )
            # PAD flags spoof
            mock_pad = MagicMock()
            mock_pad.predict.return_value = PADAssessment(
                status="suspected_spoof", score=0.15, model_name="MiniFASNetV2", explanation="Spoof detected",
            )
            svc.pad_model = mock_pad

            # Embeddings identical
            unit_vec = np.ones(512, dtype=np.float32) / np.sqrt(512)
            mock_emb = MagicMock()
            mock_emb.is_available.return_value = True
            mock_emb.get_embedding.return_value = unit_vec
            mock_emb.model_info.return_value = {"model_name": "ArcFace-w600k_r50"}
            mock_emb.get_embedding_dimension.return_value = 512
            svc.embedding_model = mock_emb

            res = svc.verify("test-id-6", doc_img, live_img)

            assert res.overall_assessment == "SUSPECTED_SPOOF"
            assert res.overall_biometric_status == "SUSPECTED_SPOOF"
            assert res.anti_spoof.status == "suspected_spoof"
            assert res.anti_spoof.score == 0.15

    def test_successful_face_match(self):
        doc_img = _dummy_image()
        live_img = _dummy_image()

        svc = FaceVerificationService()
        mock_det = MagicMock()
        mock_box = DetectedFaceBox(10, 10, 80, 80, landmarks=[(20, 25), (60, 25), (40, 45), (25, 65), (55, 65)])
        mock_det.detect_faces.return_value = MagicMock(face_count=1, faces=[mock_box], detector_used="test-det")
        mock_det.crop_face.return_value = _dummy_image(80, 80)
        svc.detector = mock_det

        with patch("app.services.face.face_verification_service.evaluate_face_quality") as mock_qual:
            mock_qual.return_value = FaceQualityResult(
                status="acceptable", blur="acceptable", brightness="acceptable", contrast="acceptable",
                face_size="acceptable", pose="acceptable", blur_score=80.0, brightness_score=120.0,
                contrast_score=30.0, width=80, height=80,
            )
            mock_pad = MagicMock()
            mock_pad.predict.return_value = PADAssessment(
                status="pass", score=0.94, model_name="MiniFASNetV2", explanation="Bona fide human",
            )
            svc.pad_model = mock_pad

            # Both produce identical 512-D vectors
            unit_vec = np.ones(512, dtype=np.float32) / np.sqrt(512)
            mock_emb = MagicMock()
            mock_emb.is_available.return_value = True
            mock_emb.get_embedding.return_value = unit_vec
            mock_emb.model_info.return_value = {"model_name": "ArcFace-w600k_r50"}
            mock_emb.get_embedding_dimension.return_value = 512
            svc.embedding_model = mock_emb

            res = svc.verify("test-id-7", doc_img, live_img)

            assert res.overall_assessment == "FACE_MATCH"
            assert res.overall_biometric_status == "FACE_MATCH"
            assert res.status == "completed"
            assert res.face_match.status == "match"
            assert res.face_match.similarity == 1.0
            assert res.anti_spoof.status == "pass"

    def test_face_mismatch(self):
        doc_img = _dummy_image()
        live_img = _dummy_image()

        svc = FaceVerificationService()
        mock_det = MagicMock()
        mock_box = DetectedFaceBox(10, 10, 80, 80, landmarks=[(20, 25), (60, 25), (40, 45), (25, 65), (55, 65)])
        mock_det.detect_faces.return_value = MagicMock(face_count=1, faces=[mock_box], detector_used="test-det")
        mock_det.crop_face.return_value = _dummy_image(80, 80)
        svc.detector = mock_det

        with patch("app.services.face.face_verification_service.evaluate_face_quality") as mock_qual:
            mock_qual.return_value = FaceQualityResult(
                status="acceptable", blur="acceptable", brightness="acceptable", contrast="acceptable",
                face_size="acceptable", pose="acceptable", blur_score=80.0, brightness_score=120.0,
                contrast_score=30.0, width=80, height=80,
            )
            mock_pad = MagicMock()
            mock_pad.predict.return_value = PADAssessment(
                status="pass", score=0.91, model_name="MiniFASNetV2", explanation="Bona fide human",
            )
            svc.pad_model = mock_pad

            # Orthogonal vectors (similarity = 0.0)
            v1 = np.zeros(512, dtype=np.float32); v1[0] = 1.0
            v2 = np.zeros(512, dtype=np.float32); v2[1] = 1.0
            mock_emb = MagicMock()
            mock_emb.is_available.return_value = True
            mock_emb.get_embedding.side_effect = [v1, v2]
            mock_emb.model_info.return_value = {"model_name": "ArcFace-w600k_r50"}
            mock_emb.get_embedding_dimension.return_value = 512
            svc.embedding_model = mock_emb

            res = svc.verify("test-id-8", doc_img, live_img)

            assert res.overall_assessment == "FACE_MISMATCH"
            assert res.overall_biometric_status == "FACE_MISMATCH"
            assert res.face_match.status == "no_match"
            assert res.face_match.similarity == 0.0

    def test_model_unavailable_when_arcface_not_ready(self):
        doc_img = _dummy_image()
        live_img = _dummy_image()

        svc = FaceVerificationService()
        mock_det = MagicMock()
        mock_box = DetectedFaceBox(10, 10, 80, 80)
        mock_det.detect_faces.return_value = MagicMock(face_count=1, faces=[mock_box], detector_used="test-det")
        mock_det.crop_face.return_value = _dummy_image(80, 80)
        svc.detector = mock_det

        with patch("app.services.face.face_verification_service.evaluate_face_quality") as mock_qual:
            mock_qual.return_value = FaceQualityResult(
                status="acceptable", blur="acceptable", brightness="acceptable", contrast="acceptable",
                face_size="acceptable", pose="acceptable", blur_score=80.0, brightness_score=120.0,
                contrast_score=30.0, width=80, height=80,
            )
            mock_pad = MagicMock()
            mock_pad.predict.return_value = PADAssessment(status="pass", score=0.90, model_name="MiniFASNet")
            svc.pad_model = mock_pad

            mock_emb = MagicMock()
            mock_emb.is_available.return_value = False
            svc.embedding_model = mock_emb

            res = svc.verify("test-id-9", doc_img, live_img)

            assert res.status == "model_unavailable"
            assert res.overall_assessment == "MODEL_UNAVAILABLE"
            assert res.overall_biometric_status == "BIOMETRIC_INCONCLUSIVE"
            assert res.face_match.status == "unavailable"

    def test_never_issues_unauthorized_clearance_words(self):
        doc_img = _dummy_image()
        live_img = _dummy_image()
        res = verify_passport_biometrics("test-id-10", "passport", doc_img, live_img)
        for text in [res.overall_assessment, res.overall_biometric_status, res.summary]:
            assert "AUTHENTICATED" not in text
            assert "PERSON IS AUTHENTIC" not in text
            assert "PASSPORT IS GENUINE" not in text
            assert "TRAVELER CLEARED" not in text
