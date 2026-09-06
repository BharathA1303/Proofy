"""
backend/tests/test_face_aligner.py

Unit tests for FaceAligner.
Validates 5-point landmark similarity transformation and bounding box fallback alignment.
"""
import numpy as np
import pytest

from app.services.face.face_aligner import ARCFACE_REFERENCE_POINTS, FaceAligner


class TestFaceAligner:
    def test_align_face_5point_exact_shape(self):
        aligner = FaceAligner()
        img = np.full((300, 300, 3), 128, dtype=np.uint8)

        # 5 sample landmark points
        landmarks = [
            (90.0, 100.0),   # left eye
            (170.0, 100.0),  # right eye
            (130.0, 140.0),  # nose
            (100.0, 190.0),  # left mouth
            (160.0, 190.0),  # right mouth
        ]

        aligned = aligner.align_face_5point(img, landmarks, (112, 112))
        assert aligned.shape == (112, 112, 3)
        assert aligned.dtype == np.uint8

    def test_align_face_invalid_landmarks(self):
        aligner = FaceAligner()
        img = np.zeros((100, 100, 3), dtype=np.uint8)

        with pytest.raises(ValueError):
            aligner.align_face_5point(img, [(10.0, 10.0)])  # only 1 landmark

    def test_align_bbox_fallback(self):
        aligner = FaceAligner()
        img = np.zeros((200, 200, 3), dtype=np.uint8)
        bbox = (20, 20, 80, 80)

        aligned = aligner.align_bbox_fallback(img, bbox, margin_pct=0.15, target_size=(112, 112))
        assert aligned.shape == (112, 112, 3)
