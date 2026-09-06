"""
backend/tests/test_national_id_parser.py

Tests for National ID OCR field parsing:
- 12-digit identity number extraction
- Bearer name extraction
- Full DOB vs. Year of Birth (YOB) explicitly separated
- Gender and address extraction
- Ambiguous identifier detection
- Unsupported layout rejection
"""
import pytest
from app.schemas.ocr import OCRRegionRaw
from app.services.documents.national_id.national_id_parser import (
    parse_national_id,
)


def _make_region(text: str, conf: float = 0.95) -> OCRRegionRaw:
    return OCRRegionRaw(text=text, confidence=conf, bbox=[[0, 0], [100, 0], [100, 20], [0, 20]])


class TestNationalIdParser:
    def test_parse_full_national_id(self):
        regions = [
            _make_region("GOVERNMENT OF INDIA"),
            _make_region("Unique Identification Authority of India"),
            _make_region("Rahul Sharma"),
            _make_region("DOB: 15/05/1992"),
            _make_region("Gender: MALE"),
            _make_region("Address: 123 Connaught Place, New Delhi 110001"),
            _make_region("9876 5432 1098"),
            _make_region("Mera Aadhaar, Meri Pehchan"),
        ]

        parsed = parse_national_id(regions)

        assert parsed.unsupported_layout is False
        assert parsed.identity_number.value == "987654321098"
        assert parsed.masked_identity_number == "XXXX XXXX 1098"
        assert parsed.name.value == "RAHUL SHARMA"
        assert parsed.dob.value == "1992-05-15"
        assert parsed.year_of_birth.value == "1992"
        assert parsed.gender.value == "MALE"
        assert "123 CONNAUGHT PLACE" in (parsed.address.value or "").upper()
        assert parsed.issuing_authority.value == "Unique Identification Authority of India"

    def test_parse_year_only_dob(self):
        regions = [
            _make_region("GOVERNMENT OF INDIA"),
            _make_region("UIDAI"),
            _make_region("Priya Patel"),
            _make_region("Year of Birth: 1995"),
            _make_region("Female"),
            _make_region("2345 6789 0123"),
        ]

        parsed = parse_national_id(regions)

        assert parsed.unsupported_layout is False
        assert parsed.name.value == "PRIYA PATEL"
        # Crucial: Year of birth only! Full DOB must remain None, never fabricated!
        assert parsed.dob.value is None
        assert parsed.year_of_birth.value == "1995"
        assert parsed.gender.value == "FEMALE"

    def test_ambiguous_identifier_detection(self):
        regions = [
            _make_region("GOVERNMENT OF INDIA"),
            _make_region("John Doe"),
            _make_region("DOB: 01/01/1985"),
            _make_region("1234 56B8 9012"),  # Letter B instead of digit
        ]

        parsed = parse_national_id(regions)
        assert parsed.is_ambiguous_identifier is True
        assert parsed.identity_number.value is None
        assert "1234 56B8 9012" in parsed.identity_number.raw

    def test_unsupported_layout_rejection(self):
        # Regions containing non-National ID text
        regions = [
            _make_region("CONFERENCE SCHEDULE"),
            _make_region("10:00 AM Keynote Speech"),
            _make_region("11:30 AM Break"),
        ]

        parsed = parse_national_id(regions)
        assert parsed.unsupported_layout is True
        assert parsed.identity_number.value is None
        assert parsed.name.value is None

    def test_header_noise_not_extracted_as_name(self):
        regions = [
            _make_region("GOVERNMENT OF INDIA"),
            _make_region("BHARAT SARKAR"),
            _make_region("UNIQUE IDENTIFICATION AUTHORITY OF INDIA"),
            _make_region("MERA AADHAAR MERI PEHCHAN"),
            _make_region("VIKRAM MALHOTRA"),
            _make_region("DOB: 20/11/1988"),
            _make_region("3456 7890 1234"),
        ]

        parsed = parse_national_id(regions)
        assert parsed.name.value == "VIKRAM MALHOTRA"
        assert parsed.name.value not in ("GOVERNMENT OF INDIA", "BHARAT SARKAR")
