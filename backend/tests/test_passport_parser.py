"""
backend/tests/test_passport_parser.py

Unit tests for the passport parser.

Design: These tests use MOCKED OCR regions — they do NOT require
PaddleOCR or PaddlePaddle to be running. The parser logic is tested
independently of the OCR engine, which has its own integration tests.

Test scenarios:
  1. Standard passport OCR output → correct field extraction
  2. MRZ line extraction
  3. MRZ field parsing (name, doc number, DOB, nationality, gender, expiry)
  4. Missing fields return None (never fabricated)
  5. No MRZ detected → MRZ fields are None
  6. OCR noise / garbage text does not crash parser
  7. Single-character gender detection
  8. Passport number pattern matching
  9. Empty regions list → all None
  10. Parser never invents values for undetected fields
"""
import pytest
from app.services.ocr.ocr_engine import OCRRegion
from app.services.ocr.passport_parser import (
    ParsedField,
    PassportParseResult,
    _extract_mrz,
    _is_mrz_candidate,
    _normalize_mrz_line,
    _parse_mrz_fields,
    parse_passport,
)


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────

def make_region(text: str, confidence: float = 0.95, top_y: int = 100) -> OCRRegion:
    """Create a mock OCR region with a simple rectangular bounding box."""
    return OCRRegion(
        text=text,
        confidence=confidence,
        bbox=[[0, top_y], [200, top_y], [200, top_y + 20], [0, top_y + 20]],
    )


def make_mrz_region(text: str, confidence: float = 0.93, top_y: int = 800) -> OCRRegion:
    """Create a mock MRZ OCR region in the bottom zone of the image."""
    return OCRRegion(
        text=text,
        confidence=confidence,
        bbox=[[0, top_y], [500, top_y], [500, top_y + 20], [0, top_y + 20]],
    )


# ──────────────────────────────────────────────
#  _is_mrz_candidate tests
# ──────────────────────────────────────────────

class TestIsMrzCandidate:
    def test_valid_mrz_line1(self):
        line = "P<INDMALHOTRA<<ASHOK<<<<<<<<<<<<<<<<<<<<<<<"
        assert _is_mrz_candidate(line) is True

    def test_valid_mrz_line2(self):
        line = "A12345671IND9001011M2912318<<<<<<<<<<<<<<<6"
        assert _is_mrz_candidate(line) is True

    def test_normal_text_rejected(self):
        assert _is_mrz_candidate("REPUBLIC OF INDIA") is False

    def test_short_text_rejected(self):
        assert _is_mrz_candidate("A1B2C3") is False

    def test_empty_string_rejected(self):
        assert _is_mrz_candidate("") is False

    def test_mostly_special_chars_rejected(self):
        # Less than 85% valid MRZ chars
        assert _is_mrz_candidate("!@#$%^&*()!@#$%^&*()!@#$%^&*()!@#$%^&*()") is False

    def test_mixed_valid_line_accepted(self):
        # 40+ chars, >85% valid MRZ chars
        line = "P<GBRDOE<<JOHN<JAMES<<<<<<<<<<<<<<<<<<<<<<"
        assert _is_mrz_candidate(line) is True


# ──────────────────────────────────────────────
#  _normalize_mrz_line tests
# ──────────────────────────────────────────────

class TestNormalizeMrzLine:
    def test_removes_spaces(self):
        result = _normalize_mrz_line("P<IND MAL HOTRA<<")
        assert " " not in result

    def test_uppercases(self):
        result = _normalize_mrz_line("p<indmalhotra<<")
        assert result == result.upper()

    def test_preserves_valid_chars(self):
        raw = "P<INDMALHOTRA<<ASHOK<<<<<<<<<<<<<<<<<<<<<<<"
        result = _normalize_mrz_line(raw)
        assert result == raw


# ──────────────────────────────────────────────
#  _parse_mrz_fields tests
# ──────────────────────────────────────────────

class TestParseMrzFields:
    # Standard Indian passport MRZ (synthetic, not a real person)
    # ICAO TD3 format: 44 characters per line
    # Line 1: P<ISS<SURNAME<<GIVEN<NAMES<<<<<<<<<<<<<<<<<<<  (44 chars)
    # Line 2: DOCNMBR0CIS YYMMDD0SEX YYMMDD0OPTIONAL DATA  0  (44 chars)
    #                ^9 chars ^check ^3   ^6      ^check
    LINE1 = "P<INDMALHOTRA<<ASHOK<KUMAR<<<<<<<<<<<<<<<<<<"  # 44 chars
    LINE2 = "A1234567<1IND9001011M2912318<<<<<<<<<<<<<<<6"  # 44 chars

    def test_name_extracted(self):
        result = _parse_mrz_fields(self.LINE1, self.LINE2)
        # Name is in line1 — surname MALHOTRA, given name ASHOK KUMAR
        assert result["name_from_mrz"] is not None
        assert "MALHOTRA" in result["name_from_mrz"]

    def test_doc_number_extracted(self):
        result = _parse_mrz_fields(self.LINE1, self.LINE2)
        # Doc number field is A1234567 (positions 0-7), filler < at 8, check digit 1 at 9
        assert result["docNumber_from_mrz"] == "A1234567"

    def test_nationality_extracted(self):
        result = _parse_mrz_fields(self.LINE1, self.LINE2)
        # Nationality at positions 10-12 = "IND"
        assert result["nationality_from_mrz"] == "IND"

    def test_dob_extracted_and_formatted(self):
        result = _parse_mrz_fields(self.LINE1, self.LINE2)
        # YYMMDD at positions 13-18 = 900101 → 01/01/1990
        assert result["dob_from_mrz"] == "01/01/1990"

    def test_gender_extracted(self):
        result = _parse_mrz_fields(self.LINE1, self.LINE2)
        # Gender at position 20 = M
        assert result["gender_from_mrz"] == "M"

    def test_expiry_extracted_and_formatted(self):
        result = _parse_mrz_fields(self.LINE1, self.LINE2)
        # YYMMDD at positions 21-26 = 291231 → 31/12/2029
        assert result["expiry_from_mrz"] == "31/12/2029"

    def test_missing_line2_returns_none_for_line2_fields(self):
        result = _parse_mrz_fields(self.LINE1, None)
        assert result["docNumber_from_mrz"] is None
        assert result["dob_from_mrz"] is None

    def test_missing_line1_returns_none_for_name(self):
        result = _parse_mrz_fields(None, self.LINE2)
        assert result["name_from_mrz"] is None

    def test_both_none_returns_all_none(self):
        result = _parse_mrz_fields(None, None)
        assert all(v is None for v in result.values())

    def test_short_line_returns_none(self):
        result = _parse_mrz_fields("P<IND", "A123")
        assert result["docNumber_from_mrz"] is None


# ──────────────────────────────────────────────
#  _extract_mrz tests
# ──────────────────────────────────────────────

class TestExtractMrz:
    LINE1_TEXT = "P<INDMALHOTRA<<ASHOK<KUMAR<<<<<<<<<<<<<<<<<"
    LINE2_TEXT = "A1234567<1IND9001011M2912318<<<<<<<<<<<<<<<6"

    def test_detects_two_mrz_lines(self):
        regions = [
            make_region("REPUBLIC OF INDIA", top_y=50),
            make_region("PASSPORT", top_y=100),
            make_mrz_region(self.LINE1_TEXT, top_y=800),
            make_mrz_region(self.LINE2_TEXT, top_y=830),
        ]
        line1, line2 = _extract_mrz(regions, image_height=1000)
        assert line1.value is not None
        assert line2.value is not None

    def test_no_mrz_regions_returns_none(self):
        regions = [
            make_region("REPUBLIC OF INDIA", top_y=50),
            make_region("PASSPORT", top_y=100),
            make_region("DOE JOHN", top_y=200),
        ]
        line1, line2 = _extract_mrz(regions, image_height=1000)
        assert line1.value is None
        assert line2.value is None

    def test_only_one_mrz_line(self):
        regions = [
            make_region("REPUBLIC OF INDIA", top_y=50),
            make_mrz_region(self.LINE1_TEXT, top_y=800),
        ]
        line1, line2 = _extract_mrz(regions, image_height=1000)
        assert line1.value is not None
        assert line2.value is None


# ──────────────────────────────────────────────
#  parse_passport (integration) tests
# ──────────────────────────────────────────────

class TestParsePassport:
    """End-to-end parser tests with mock OCR regions."""

    LINE1_TEXT = "P<INDMALHOTRA<<ASHOK<KUMAR<<<<<<<<<<<<<<<<<"
    LINE2_TEXT = "A1234567<1IND9001011M2912318<<<<<<<<<<<<<<<6"

    def _make_full_passport_regions(self) -> list[OCRRegion]:
        """Simulate a realistic set of OCR regions from a passport scan."""
        return [
            make_region("REPUBLIC OF INDIA", top_y=30),
            make_region("PASSPORT", top_y=60),
            make_region("Surname", top_y=150),
            make_region("MALHOTRA", top_y=175),
            make_region("Given Name(s)", top_y=220),
            make_region("ASHOK KUMAR", top_y=245),
            make_region("Nationality", top_y=290),
            make_region("INDIAN", top_y=315),
            make_region("Date of Birth", top_y=360),
            make_region("01/01/1990", top_y=385),
            make_region("Sex", top_y=430),
            make_region("M", top_y=455),
            make_region("Place of Birth", top_y=500),
            make_region("DELHI", top_y=525),
            make_region("Date of Issue", top_y=570),
            make_region("10/03/2020", top_y=595),
            make_region("Date of Expiry", top_y=640),
            make_region("09/03/2030", top_y=665),
            make_region("Issuing Authority", top_y=710),
            make_region("DELHI RPO", top_y=735),
            make_region("A1234567", top_y=780, confidence=0.98),
            make_mrz_region(self.LINE1_TEXT, top_y=850),
            make_mrz_region(self.LINE2_TEXT, top_y=880),
        ]

    def test_mrz_extracted(self):
        regions = self._make_full_passport_regions()
        result = parse_passport(regions, image_height=1000)
        assert result.mrz_line1.value is not None
        assert result.mrz_line2.value is not None

    def test_doc_number_extracted_from_mrz(self):
        regions = self._make_full_passport_regions()
        result = parse_passport(regions, image_height=1000)
        assert result.docNumber.value == "A1234567"

    def test_nationality_extracted(self):
        regions = self._make_full_passport_regions()
        result = parse_passport(regions, image_height=1000)
        # MRZ-derived nationality (IND) takes priority over VIZ (INDIAN)
        assert result.nationality.value == "IND"

    def test_dob_from_mrz(self):
        regions = self._make_full_passport_regions()
        result = parse_passport(regions, image_height=1000)
        # MRZ-derived: position 13-18 in LINE2 = 900101 → 01/01/1990
        assert result.dob.value == "01/01/1990"

    def test_gender_from_mrz(self):
        regions = self._make_full_passport_regions()
        result = parse_passport(regions, image_height=1000)
        assert result.gender.value == "M"

    def test_expiry_from_mrz(self):
        regions = self._make_full_passport_regions()
        result = parse_passport(regions, image_height=1000)
        # MRZ-derived expiry (31/12/2029) should take priority over VIZ (09/03/2030)
        assert result.expiry.value == "31/12/2029"

    def test_empty_regions_all_none(self):
        """CRITICAL: Parser must not invent values when OCR returns nothing."""
        result = parse_passport([], image_height=1000)
        assert result.name.value is None
        assert result.docNumber.value is None
        assert result.dob.value is None
        assert result.nationality.value is None
        assert result.gender.value is None
        assert result.expiry.value is None
        assert result.mrz_line1.value is None
        assert result.mrz_line2.value is None

    def test_garbage_ocr_does_not_crash(self):
        """Parser must handle noisy / garbage OCR without raising exceptions."""
        regions = [
            make_region("@#$%^&*", top_y=100),
            make_region("|||||||||||||||||||||||||||||||||||||||||||", top_y=200),
            make_region("  ", top_y=300),
            make_region("12345", top_y=400),
        ]
        # Should not raise
        result = parse_passport(regions, image_height=1000)
        assert isinstance(result, PassportParseResult)

    def test_no_mrz_fields_are_none(self):
        """When no MRZ is found, MRZ fields must be None, not empty strings."""
        regions = [
            make_region("REPUBLIC OF INDIA", top_y=50),
            make_region("PASSPORT", top_y=100),
        ]
        result = parse_passport(regions, image_height=1000)
        assert result.mrz_line1.value is None
        assert result.mrz_line2.value is None

    def test_low_confidence_regions_still_extracted(self):
        """Even low-confidence regions should be attempted (caller decides threshold)."""
        regions = [
            make_mrz_region(self.LINE1_TEXT, confidence=0.55, top_y=800),
            make_mrz_region(self.LINE2_TEXT, confidence=0.52, top_y=830),
        ]
        result = parse_passport(regions, image_height=1000)
        assert result.mrz_line1.value is not None

    def test_parser_never_adds_fake_name(self):
        """Specifically verify that no hardcoded/fake name is ever returned."""
        result = parse_passport([], image_height=1000)
        fake_names = ["John Doe", "Unknown", "Test User", "Sample", "N/A"]
        assert result.name.value not in fake_names
        assert result.name.value is None

    def test_file_number_extracted(self):
        """Indian passport file numbers (2 letters + 13-16 digits) are extracted from VIZ."""
        regions = self._make_full_passport_regions() + [
            make_region("File Number", top_y=930),
            make_region("DL0012345671234", top_y=955),
        ]
        result = parse_passport(regions, image_height=1000)
        assert result.fileNumber.value == "DL0012345671234"

    def test_file_number_absent_is_none(self):
        """When no file number is present in OCR output, it stays None (not fabricated)."""
        regions = self._make_full_passport_regions()
        result = parse_passport(regions, image_height=1000)
        assert result.fileNumber.value is None

    def test_place_of_issue_extracted_via_keyword(self):
        """Place of Issue is located via keyword-anchored bbox geometry, below the label."""
        regions = self._make_full_passport_regions() + [
            make_region("Place of Issue", top_y=930),
            make_region("NEW DELHI", top_y=955),
        ]
        result = parse_passport(regions, image_height=1000)
        assert result.placeOfIssue.value == "NEW DELHI"

    def test_place_of_issue_absent_is_none(self):
        regions = self._make_full_passport_regions()
        result = parse_passport(regions, image_height=1000)
        assert result.placeOfIssue.value is None
