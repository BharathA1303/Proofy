"""
backend/tests/test_forensic_compression.py

Unit tests for Module 3 local compression consistency analysis.
"""
from app.services.forensics.compression_analysis import RegionBox, analyze_local_compression
from tests.forensic_test_utils import decode_jpeg, encode_jpeg, make_textured_image, recompress_region


class TestCompressionAnalysis:
    def test_uniform_image_is_normal(self):
        img = make_textured_image()
        jpeg_bytes = encode_jpeg(img, quality=90)
        decoded = decode_jpeg(jpeg_bytes)

        regions = {
            "photo": RegionBox(x=60, y=160, width=220, height=220),
            "mrz": RegionBox(x=60, y=1000, width=700, height=100),
            "background": RegionBox(x=600, y=100, width=200, height=150),
        }
        result = analyze_local_compression(decoded, regions)
        assert result.status in ("normal", "insufficient_data")

    def test_locally_recompressed_region_is_flagged(self):
        img = make_textured_image()
        jpeg_bytes = encode_jpeg(img, quality=95)
        decoded = decode_jpeg(jpeg_bytes)

        photo_box = (60, 160, 220, 220)
        tampered = recompress_region(decoded, box=photo_box, quality=8)
        tampered_bytes = encode_jpeg(tampered, quality=95)
        tampered_decoded = decode_jpeg(tampered_bytes)

        regions = {
            "photo": RegionBox(x=60, y=160, width=220, height=220),
            "mrz": RegionBox(x=60, y=1000, width=700, height=100),
            "background": RegionBox(x=600, y=100, width=200, height=150),
        }
        result = analyze_local_compression(tampered_decoded, regions)
        assert result.status == "suspicious"

    def test_none_regions_are_skipped_without_error(self):
        img = make_textured_image()
        jpeg_bytes = encode_jpeg(img, quality=90)
        decoded = decode_jpeg(jpeg_bytes)

        regions = {
            "photo": None,
            "mrz": RegionBox(x=60, y=1000, width=700, height=100),
            "background": RegionBox(x=600, y=100, width=200, height=150),
        }
        result = analyze_local_compression(decoded, regions)
        assert result.scores["photo"] is None
        assert result.status in ("normal", "suspicious", "insufficient_data")

    def test_too_few_regions_is_insufficient_data(self):
        img = make_textured_image()
        jpeg_bytes = encode_jpeg(img, quality=90)
        decoded = decode_jpeg(jpeg_bytes)

        regions = {"photo": None, "mrz": None, "background": RegionBox(x=600, y=100, width=200, height=150)}
        result = analyze_local_compression(decoded, regions)
        assert result.status == "insufficient_data"
