"""
backend/tests/test_forensic_ela.py

Unit tests for Module 3 Error Level Analysis (ELA).
"""
import numpy as np

from app.services.forensics.ela import run_ela
from tests.forensic_test_utils import (
    decode_jpeg,
    encode_jpeg,
    make_textured_image,
)


def _inject_high_frequency_patch(img: np.ndarray, box: tuple[int, int, int, int], seed: int = 99) -> np.ndarray:
    """
    Paste deterministic high-frequency random noise into a region — simulating
    content spliced in from a different source. JPEG recompression quantizes
    high-frequency content more aggressively, so this region shows a distinct
    local error signature from the smoother surrounding background.
    """
    x, y, w, h = box
    out = img.copy()
    rng = np.random.default_rng(seed)
    noise = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
    out[y:y + h, x:x + w] = noise
    return out


class TestELA:
    def test_unmodified_image_is_normal(self):
        """
        A synthetic image saved once at the same quality ELA recompresses at
        should show a low, roughly uniform error level with no flagged regions.
        """
        img = make_textured_image()
        # Round-trip through JPEG once so the "original" itself is already a
        # single-generation JPEG (as a real upload would be).
        jpeg_bytes = encode_jpeg(img, quality=90)
        decoded = decode_jpeg(jpeg_bytes)

        result = run_ela(decoded)

        assert result.status == "normal"
        assert result.flagged_area_ratio < 0.02

    def test_modified_region_is_flagged(self):
        """
        A region with spliced-in high-frequency content should produce a
        locally elevated ELA error relative to the smoother surrounding
        background, and be flagged as a suspicious region.
        """
        img = make_textured_image()
        tampered = _inject_high_frequency_patch(img, box=(300, 400, 200, 200))
        tampered_bytes = encode_jpeg(tampered, quality=90)
        tampered_decoded = decode_jpeg(tampered_bytes)

        result = run_ela(tampered_decoded)

        assert result.status == "suspicious"
        assert result.flagged_area_ratio > 0
        assert len(result.regions) > 0

    def test_ela_is_deterministic(self):
        img = make_textured_image()
        jpeg_bytes = encode_jpeg(img, quality=90)
        decoded = decode_jpeg(jpeg_bytes)

        r1 = run_ela(decoded)
        r2 = run_ela(decoded)

        assert r1.mean_error == r2.mean_error
        assert r1.max_error == r2.max_error
        assert r1.flagged_area_ratio == r2.flagged_area_ratio
        assert [(r.x, r.y, r.width, r.height) for r in r1.regions] == \
               [(r.x, r.y, r.width, r.height) for r in r2.regions]

    def test_suspicious_region_coordinates_are_valid(self):
        img = make_textured_image()
        tampered = _inject_high_frequency_patch(img, box=(300, 400, 200, 200))
        tampered_bytes = encode_jpeg(tampered, quality=90)
        tampered_decoded = decode_jpeg(tampered_bytes)

        h, w = tampered_decoded.shape[:2]
        result = run_ela(tampered_decoded)

        for region in result.regions:
            assert 0 <= region.x < w
            assert 0 <= region.y < h
            assert region.x + region.width <= w
            assert region.y + region.height <= h
            assert region.width > 0 and region.height > 0
