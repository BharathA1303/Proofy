"""
backend/tests/test_face_quality.py

Unit tests for face quality evaluation gate (document & live camera).
"""
import numpy as np
import cv2
from app.services.face.face_quality import evaluate_face_quality
from app.core.config import settings


def _create_synthetic_face(w=120, h=140, brightness=130, blur_ksize=0):
    """Generate a clean synthetic grayscale face pattern with controllable parameters."""
    img = np.full((h, w, 3), brightness, dtype=np.uint8)
    # Draw face features to introduce texture and contrast
    cv2.circle(img, (w // 2, h // 2), min(w, h) // 3, (brightness - 30, brightness - 30, brightness - 30), -1)
    cv2.circle(img, (w // 3, h // 3), 10, (20, 20, 20), -1)
    cv2.circle(img, (2 * w // 3, h // 3), 10, (20, 20, 20), -1)
    cv2.line(img, (w // 3, 2 * h // 3), (2 * w // 3, 2 * h // 3), (20, 20, 20), 4)

    if blur_ksize > 0:
        img = cv2.GaussianBlur(img, (blur_ksize, blur_ksize), 0)
    return img


class TestFaceQuality:
    def test_acceptable_face_quality(self):
        img = _create_synthetic_face(120, 140, brightness=130)
        res = evaluate_face_quality(img, is_document=False)
        assert res.status == "acceptable"
        assert res.blur == "acceptable"
        assert res.brightness == "acceptable"
        assert res.contrast == "acceptable"
        assert res.face_size == "acceptable"
        assert res.pose == "acceptable"
        assert res.error_code is None

    def test_too_blurry_face_rejected(self):
        # Heavy Gaussian blur reduces Laplacian variance below threshold
        blurry = _create_synthetic_face(120, 140, brightness=130, blur_ksize=25)
        res = evaluate_face_quality(blurry, is_document=False)
        assert res.status == "poor"
        assert res.blur == "poor"
        assert "blurry" in res.explanation.lower() or "hold still" in res.explanation.lower()
        assert res.error_code == "FACE_TOO_BLURRY"

    def test_too_dark_face_rejected(self):
        dark = np.full((120, 120, 3), 15, dtype=np.uint8)
        res = evaluate_face_quality(dark, is_document=False)
        assert res.status == "poor"
        assert res.brightness == "poor"
        assert res.error_code == "FACE_TOO_DARK"
        assert "dark" in res.explanation.lower()

    def test_too_bright_face_rejected(self):
        bright = np.full((120, 120, 3), 245, dtype=np.uint8)
        res = evaluate_face_quality(bright, is_document=False)
        assert res.status == "poor"
        assert res.brightness == "poor"
        assert res.error_code == "FACE_TOO_BRIGHT"
        assert "overexposed" in res.explanation.lower()

    def test_too_small_face_rejected(self):
        small = _create_synthetic_face(35, 40, brightness=130)
        res = evaluate_face_quality(small, is_document=False)
        assert res.status == "poor"
        assert res.face_size == "poor"
        assert res.error_code == "FACE_TOO_SMALL"

    def test_empty_or_none_face(self):
        res = evaluate_face_quality(None, is_document=True)
        assert res.status == "unavailable"
        assert res.error_code == "DOCUMENT_FACE_QUALITY_INSUFFICIENT"
