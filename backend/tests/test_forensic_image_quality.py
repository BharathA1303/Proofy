"""
backend/tests/test_forensic_image_quality.py

Unit tests for Module 3 image quality assessment.
"""
from app.services.forensics.image_quality import assess_image_quality
from tests.forensic_test_utils import (
    make_blurred,
    make_dark,
    make_textured_image,
    make_tiny,
)


class TestImageQualityAssessment:
    def test_valid_high_quality_image_is_adequate(self):
        img = make_textured_image()
        result = assess_image_quality(img)
        assert result.status == "adequate"
        assert result.reasons == []
        assert result.metrics["width"] > 0
        assert result.metrics["height"] > 0

    def test_very_low_resolution_image_is_insufficient(self):
        img = make_tiny(make_textured_image(), size=(80, 100))
        result = assess_image_quality(img)
        assert result.status == "insufficient"
        assert any("resolution" in r.lower() for r in result.reasons)

    def test_extremely_blurred_image_is_insufficient(self):
        img = make_blurred(make_textured_image(), ksize=41)
        result = assess_image_quality(img)
        assert result.status == "insufficient"
        assert any("blurred" in r.lower() for r in result.reasons)

    def test_very_dark_image_is_insufficient(self):
        img = make_dark(make_textured_image(), factor=0.05)
        result = assess_image_quality(img)
        assert result.status == "insufficient"
        assert any("dark" in r.lower() for r in result.reasons)

    def test_metrics_are_deterministic(self):
        img = make_textured_image()
        r1 = assess_image_quality(img)
        r2 = assess_image_quality(img)
        assert r1.metrics == r2.metrics
        assert r1.status == r2.status
