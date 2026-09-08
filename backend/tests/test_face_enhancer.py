"""
backend/tests/test_face_enhancer.py

Unit tests for DocumentFaceEnhancer (Inbuilt Super-Resolution & Quality Layer).
"""
import numpy as np
import pytest

from app.services.face.face_enhancer import DocumentFaceEnhancer


class TestDocumentFaceEnhancer:
    def test_enhance_small_portrait_upscaling(self):
        # 60x70 tiny crop (typical low-res credential crop)
        small_crop = np.full((70, 60, 3), 120, dtype=np.uint8)
        # Put some synthetic features
        small_crop[25:35, 20:40] = 50

        enhanced = DocumentFaceEnhancer.enhance_portrait_crop(small_crop, target_min_dim=300)
        assert enhanced is not None
        assert enhanced.shape[0] >= 300 or enhanced.shape[1] >= 300
        assert enhanced.dtype == np.uint8

    def test_color_cast_balancing(self):
        # Heavy cyan/blue tint image (common in photocopied/scanned IDs)
        blue_tinted = np.zeros((100, 100, 3), dtype=np.uint8)
        blue_tinted[:, :, 0] = 200  # Blue
        blue_tinted[:, :, 1] = 160  # Green
        blue_tinted[:, :, 2] = 80   # Red

        balanced = DocumentFaceEnhancer._balance_color_cast(blue_tinted)
        assert balanced is not None
        assert balanced.shape == (100, 100, 3)
        # Red should be boosted, blue should be attenuated
        assert balanced[:, :, 2].mean() > 80
        assert balanced[:, :, 0].mean() < 200

    def test_empty_or_none_crop(self):
        assert DocumentFaceEnhancer.enhance_portrait_crop(None) is None
        empty = np.zeros((0, 0, 3), dtype=np.uint8)
        assert DocumentFaceEnhancer.enhance_portrait_crop(empty).size == 0
