"""
backend/tests/test_forensic_metadata.py

Unit tests for Module 3 metadata analysis.
"""
from app.services.forensics.metadata_analysis import analyze_metadata
from tests.forensic_test_utils import make_textured_image, pil_jpeg_bytes_no_exif, pil_jpeg_bytes_with_exif


class TestMetadataAnalysis:
    def test_image_with_metadata_is_available(self):
        img = make_textured_image()
        jpeg_bytes = pil_jpeg_bytes_with_exif(img)
        result = analyze_metadata(jpeg_bytes)
        assert result.status == "available"
        assert len(result.fields_present) > 0

    def test_image_without_metadata_is_absent_not_suspicious(self):
        img = make_textured_image()
        jpeg_bytes = pil_jpeg_bytes_no_exif(img)
        result = analyze_metadata(jpeg_bytes)
        assert result.status == "absent"
        # Absence must never be reported as "suspicious".
        assert result.status != "suspicious"

    def test_editor_software_tag_is_suspicious_but_not_fatal(self):
        img = make_textured_image()
        jpeg_bytes = pil_jpeg_bytes_with_exif(img, software="Adobe Photoshop 25.0")
        result = analyze_metadata(jpeg_bytes)
        assert result.status == "suspicious"
        assert result.severity in ("low", "medium")
