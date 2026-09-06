"""
tests/test_visa_parser.py

Tests for Visa OCR parser (deterministic extraction, regex label parsing,
bounding box preservation, confidence tracking, and optional MRV detection).
"""
import pytest
from app.schemas.ocr import OCRRegionRaw
from app.services.documents.visa.visa_parser import (
    ParsedVisaData,
    parse_visa,
)


def _make_region(text: str, conf: float = 0.95, top: int = 100) -> OCRRegionRaw:
    return OCRRegionRaw(
        text=text,
        confidence=conf,
        bbox=[[10, top], [200, top], [200, top + 30], [10, top + 30]],
    )


class TestVisaParser:
    def test_parse_visa_empty_regions(self):
        result = parse_visa([])
        assert isinstance(result, ParsedVisaData)
        assert result.docNumber.value is None
        assert result.name.value is None

    def test_parse_visa_viz_fields(self):
        regions = [
            _make_region("UNITED STATES OF AMERICA", 0.99, top=50),
            _make_region("VISA", 0.98, top=90),
            _make_region("VISA NO: E12345678", 0.97, top=130),
            _make_region("PASSPORT NO: P9876543", 0.96, top=170),
            _make_region("NAME: SARAH JANE CONNOR", 0.95, top=210),
            _make_region("DATE OF BIRTH: 1985-05-12", 0.96, top=250),
            _make_region("NATIONALITY: USA", 0.94, top=290),
            _make_region("VISA TYPE: B1/B2", 0.95, top=330),
            _make_region("ENTRIES: M", 0.93, top=370),
            _make_region("ISSUE DATE: 2023-01-15", 0.96, top=410),
            _make_region("EXPIRY DATE: 2033-01-15", 0.97, top=450),
            _make_region("AUTHORITY: EMBASSY LONDON", 0.92, top=490),
        ]

        parsed = parse_visa(regions, image_height=1000)
        assert parsed.docNumber.value == "E12345678"
        assert parsed.docNumber.confidence == 0.97
        assert parsed.passportNumber.value == "P9876543"
        assert parsed.name.value == "SARAH JANE CONNOR"
        assert parsed.dob.value == "1985-05-12"
        assert parsed.nationality.value == "USA"
        assert parsed.visaType.value == "B1/B2"
        assert parsed.entries.value == "MULTIPLE"
        assert parsed.issuedDate.value == "2023-01-15"
        assert parsed.expiry.value == "2033-01-15"
        assert parsed.authority.value == "EMBASSY LONDON"

    def test_parse_visa_date_formats_normalized(self):
        """Slash and dot date formats normalized to ISO YYYY-MM-DD."""
        regions = [
            _make_region("VISA NUMBER: V88776655", 0.95, top=100),
            _make_region("ISSUE DATE: 15/01/2023", 0.95, top=200),
            _make_region("EXPIRY DATE: 15.01.2028", 0.95, top=300),
            _make_region("BIRTH DATE: 1990/08/20", 0.95, top=400),
        ]
        parsed = parse_visa(regions, image_height=1000)
        assert parsed.docNumber.value == "V88776655"
        assert parsed.issuedDate.value == "2023-01-15"
        assert parsed.expiry.value == "2028-01-15"
        assert parsed.dob.value == "1990-08-20"

    def test_parse_visa_missing_fields_never_hallucinated(self):
        """When fields are absent in OCR text, values must remain None."""
        regions = [
            _make_region("VISA NO: V123456", 0.90, top=100),
            _make_region("EXPIRY DATE: 2029-12-31", 0.92, top=200),
        ]
        parsed = parse_visa(regions, image_height=1000)
        assert parsed.docNumber.value == "V123456"
        assert parsed.expiry.value == "2029-12-31"
        assert parsed.name.value is None
        assert parsed.passportNumber.value is None
        assert parsed.dob.value is None
        assert parsed.entries.value is None

    def test_parse_visa_with_optional_mrv(self):
        """Visa with machine-readable lines extracts them properly."""
        mrv_line1 = "VNUSAEXAMPLE<<JOHN<<<<<<<<<<<<<<<<<<<<<<<<<<"
        mrv_line2 = "V1234567<8USA8001014M2912318<<<<<<<<<<<<<<02"
        regions = [
            _make_region("VISA", 0.95, top=100),
            _make_region(mrv_line1, 0.92, top=850),
            _make_region(mrv_line2, 0.91, top=890),
        ]
        parsed = parse_visa(regions, image_height=1000)
        assert parsed.mrz_line1.value == mrv_line1
        assert parsed.mrz_line2.value == mrv_line2
