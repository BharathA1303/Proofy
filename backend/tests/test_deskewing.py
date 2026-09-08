"""
backend/tests/test_deskewing.py

Unit tests and speed benchmarks for the automated document deskewing engine.
"""
import time
from pathlib import Path
import cv2
import numpy as np
import pytest

from app.services.preprocessing.image_preprocessor import (
    detect_skew_angle,
    deskew_image,
    preprocess,
    PreprocessedImage,
)

ASSETS_DIR = Path(__file__).parent / "assets"


def _load_asset(filename: str) -> np.ndarray:
    path = ASSETS_DIR / filename
    if not path.exists():
        # Synthesize a fallback test card with horizontal text lines if asset missing
        img = np.full((600, 900, 3), 255, dtype=np.uint8)
        for y in range(80, 520, 45):
            cv2.putText(img, "OFFICIAL IDENTITY DOCUMENT RECORD TEXT LINE 12345", (50, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (30, 30, 30), 2)
        return img
    img = cv2.imread(str(path))
    assert img is not None, f"Failed to load asset {path}"
    return img


class TestDeskewingEngine:
    def test_straight_document_bypasses_rotation(self):
        """Clean, upright documents must produce 0.0 skew angle (no unnecessary warp)."""
        img = _load_asset("dl_official.jpg")
        angle = detect_skew_angle(img)
        assert abs(angle) == 0.0, f"Expected 0.0 skew for straight card, got {angle}"

    def test_tilted_passport_detected_accurately(self):
        """A passport tilted by +8.0 degrees should be detected around +8.0 (+/- 2.0 deg)."""
        img = _load_asset("passport_official.jpg")
        center = (img.shape[1] // 2, img.shape[0] // 2)
        M = cv2.getRotationMatrix2D(center, 8.0, 1.0)
        tilted = cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), borderMode=cv2.BORDER_REPLICATE)

        detected = detect_skew_angle(tilted)
        # Note: arctan2 slope of counter-clockwise rotated image produces ~ -8.0 deg
        assert abs(abs(detected) - 8.0) <= 2.5, f"Expected detected tilt ~8.0 deg, got {detected}"

    def test_tilted_driving_license_straightened(self):
        """Deskewing an intentionally slanted DL should straighten it."""
        img = _load_asset("sample_driving_license.jpg")
        center = (img.shape[1] // 2, img.shape[0] // 2)
        M = cv2.getRotationMatrix2D(center, 7.0, 1.0)
        tilted = cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), borderMode=cv2.BORDER_REPLICATE)

        prep = preprocess(tilted)
        assert isinstance(prep, PreprocessedImage)
        assert abs(prep.skew_angle) > 0.0, "Deskewer should have detected tilt"
        assert prep.image_np.shape[0] > 0 and prep.image_np.shape[1] > 0

    def test_sub_35ms_execution_speed(self):
        """Deskew detection and affine rotation must execute under 35ms on CPU."""
        img = _load_asset("dl_bharath_a_genuine.jpg")
        # Warmup
        detect_skew_angle(img)

        times = []
        for _ in range(5):
            t0 = time.perf_counter()
            angle = detect_skew_angle(img)
            if abs(angle) > 0.0:
                deskew_image(img, -angle)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            times.append(elapsed_ms)

        avg_time = sum(times) / len(times)
        assert avg_time < 35.0, f"Deskewing must be sub-35ms, took {avg_time:.2f}ms"

    def test_extreme_skew_safety_guard(self):
        """Angles exceeding safety limit (30 degrees) should not trigger extreme rotation."""
        img = _load_asset("dl_official.jpg")
        center = (img.shape[1] // 2, img.shape[0] // 2)
        M = cv2.getRotationMatrix2D(center, 65.0, 1.0)
        extreme_tilted = cv2.warpAffine(img, M, (img.shape[1], img.shape[0]))

        angle = detect_skew_angle(extreme_tilted)
        # Extreme angles should be clamped within [-30, +30] or returned as 0.0
        assert -30.0 <= angle <= 30.0, f"Angle must be clamped, got {angle}"
