"""
backend/tests/test_face_detector.py

Unit tests for FaceDetector engine.
"""
import numpy as np
from unittest.mock import MagicMock, patch
from app.services.face.face_detector import FaceDetector, DetectedFaceBox


class TestFaceDetector:
    def test_detector_readiness(self):
        detector = FaceDetector()
        assert detector.is_ready() is True

    def test_zero_faces_on_blank_image(self):
        detector = FaceDetector()
        blank = np.full((300, 300, 3), 128, dtype=np.uint8)
        res_live = detector.detect_faces(blank, is_document=False)
        assert res_live.face_count == 0
        assert res_live.error_code == "FACE_NOT_DETECTED"
        assert res_live.has_single_face is False

        res_doc = detector.detect_faces(blank, is_document=True)
        assert res_doc.face_count == 0
        assert res_doc.error_code == "DOCUMENT_FACE_NOT_FOUND"

    def test_none_or_empty_image(self):
        detector = FaceDetector()
        res = detector.detect_faces(None, is_document=True)
        assert res.face_count == 0
        assert res.error_code == "DOCUMENT_FACE_NOT_FOUND"

        empty = np.zeros((0, 0, 3), dtype=np.uint8)
        res2 = detector.detect_faces(empty, is_document=False)
        assert res2.face_count == 0
        assert res2.error_code == "FACE_NOT_DETECTED"

    def test_multiple_faces_detected(self):
        detector = FaceDetector()
        img = np.zeros((400, 400, 3), dtype=np.uint8)

        mock_cascade = MagicMock()
        mock_cascade.empty.return_value = False
        mock_cascade.detectMultiScale.return_value = np.array([
            [50, 50, 80, 80],
            [200, 200, 85, 85],
        ])
        detector._cascade = mock_cascade

        res = detector.detect_faces(img, min_size=60)
        assert res.face_count == 2
        assert res.error_code == "MULTIPLE_FACES_DETECTED"
        assert res.has_single_face is False
        assert len(res.faces) == 2

    def test_single_face_detected(self):
        detector = FaceDetector()
        img = np.zeros((400, 400, 3), dtype=np.uint8)

        mock_cascade = MagicMock()
        mock_cascade.empty.return_value = False
        mock_cascade.detectMultiScale.return_value = np.array([
            [60, 60, 100, 100],
        ])
        detector._cascade = mock_cascade

        res = detector.detect_faces(img, min_size=60)
        assert res.face_count == 1
        assert res.error_code is None
        assert res.has_single_face is True
        assert res.faces[0].width == 100


    def test_crop_face_stays_within_bounds(self):
        img = np.zeros((300, 300, 3), dtype=np.uint8)
        box = DetectedFaceBox(x=5, y=5, width=50, height=50)
        crop = FaceDetector.crop_face(img, box, margin_ratio=0.2)
        assert crop.shape[0] > 0
        assert crop.shape[1] > 0
        assert crop.shape[0] <= 300
        assert crop.shape[1] <= 300
