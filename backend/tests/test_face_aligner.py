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

    def test_canonical_rigid_bone_mask(self):
        mask = FaceAligner.get_canonical_rigid_bone_mask((112, 112))
        assert mask.shape == (112, 112, 1)
        assert mask.dtype == np.float32
        assert np.all(mask >= 0.0) and np.all(mask <= 1.0)

        # Center (nasal/orbital bone region ~ y:60, x:56) should be near 1.0
        center_val = float(mask[60, 56, 0])
        assert center_val > 0.90, f"Central bone mask value should be near 1.0, got {center_val}"

        # Top corner (peripheral hair/background region ~ y:5, x:5) should be near 0.0
        corner_val = float(mask[5, 5, 0])
        assert corner_val < 0.10, f"Peripheral hair value should be near 0.0, got {corner_val}"

    def test_apply_rigid_bone_mask_attenuates_hair_periphery(self):
        # Create an image with bright hair region (top) and dark face (center)
        face_img = np.full((112, 112, 3), 50, dtype=np.uint8)
        # Top 20 rows are "hair" with high intensity
        face_img[0:20, :] = 240

        masked = FaceAligner.apply_rigid_bone_mask(face_img, background_fill=128)
        assert masked.shape == (112, 112, 3)
        assert masked.dtype == np.uint8

        # In central face region, intensity should remain close to 50
        assert abs(int(masked[60, 56, 0]) - 50) < 15
        # In hair region (top row), intensity should be attenuated towards neutral 128
        assert int(masked[2, 56, 0]) < 180

    def test_compute_cranial_bone_ratios(self):
        # Canonical reference points
        landmarks = [
            (38.3, 51.7),  # left eye
            (73.5, 51.5),  # right eye
            (56.0, 71.7),  # nose tip
            (41.5, 92.4),  # left mouth
            (70.7, 92.2),  # right mouth
        ]
        ratios = FaceAligner.compute_cranial_bone_ratios(landmarks)
        assert ratios["valid"] is True
        assert ratios["interocular_dist"] > 30.0
        assert ratios["facial_height"] > 35.0
        assert 0.70 < ratios["cranial_triangle_ratio"] < 1.20
        assert ratios["bilateral_symmetry"] > 0.85

    def test_compare_cranial_structures(self):
        landmarks_a = [
            (38.3, 51.7), (73.5, 51.5), (56.0, 71.7), (41.5, 92.4), (70.7, 92.2),
        ]
        # Same proportions, slightly scaled
        landmarks_b = [
            (38.3 * 1.05, 51.7 * 1.05),
            (73.5 * 1.05, 51.5 * 1.05),
            (56.0 * 1.05, 71.7 * 1.05),
            (41.5 * 1.05, 92.4 * 1.05),
            (70.7 * 1.05, 92.2 * 1.05),
        ]

        ratios_a = FaceAligner.compute_cranial_bone_ratios(landmarks_a)
        ratios_b = FaceAligner.compute_cranial_bone_ratios(landmarks_b)

        score, is_consistent = FaceAligner.compare_cranial_structures(ratios_a, ratios_b)
        assert is_consistent is True
        assert score > 0.90
