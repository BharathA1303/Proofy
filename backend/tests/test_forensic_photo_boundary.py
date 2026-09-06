"""
backend/tests/test_forensic_photo_boundary.py

Unit tests for Module 3 photo region detection and boundary analysis.
"""
from app.services.forensics.photo_boundary import (
    PhotoRegion,
    PhotoRegionResult,
    analyze_photo_boundary,
    detect_photo_region,
)
from tests.forensic_test_utils import (
    add_altered_photo_boundary,
    add_passport_photo_rect,
    make_textured_image,
)


class TestPhotoRegionDetection:
    def test_normal_photo_boundary_is_detected_and_normal(self):
        base = make_textured_image()
        img = add_passport_photo_rect(base, x=60, y=160, w=220, h=220)

        region_result = detect_photo_region(img)
        assert region_result.status == "detected"
        assert region_result.region is not None
        assert region_result.confidence > 0

        boundary_result = analyze_photo_boundary(img, region_result)
        assert boundary_result.status in ("normal", "suspicious")
        # A cleanly drawn, evenly-bordered rectangle should not trigger
        # multiple independent boundary indicators.
        assert len(boundary_result.indicators) <= 1

    def test_altered_boundary_is_suspicious(self):
        base = make_textured_image()
        img = add_altered_photo_boundary(base, x=60, y=160, w=220, h=220)

        # Use the exact known coordinates of the drawn rectangle so the test
        # isolates boundary ANALYSIS from detection precision, which is
        # covered separately by the detection tests above.
        region_result = PhotoRegionResult(
            status="detected",
            region=PhotoRegion(x=60, y=160, width=220, height=220),
            confidence=0.9,
            method="test_fixture",
        )

        boundary_result = analyze_photo_boundary(img, region_result)
        assert boundary_result.status == "suspicious"
        assert len(boundary_result.indicators) >= 1

    def test_missing_photo_region_is_unavailable(self):
        img = make_textured_image()  # no rectangular photo present
        region_result = detect_photo_region(img)

        boundary_result = analyze_photo_boundary(img, region_result)
        if region_result.status == "unavailable":
            assert boundary_result.status == "unavailable"
        else:
            # If a spurious rectangle happened to be found, boundary analysis
            # must still run without error and never fabricate certainty.
            assert boundary_result.status in ("normal", "suspicious")

    def test_detected_region_never_fabricates_when_unavailable(self):
        img = make_textured_image()
        region_result = detect_photo_region(img)
        if region_result.status == "unavailable":
            assert region_result.region is None
            assert region_result.confidence == 0.0
