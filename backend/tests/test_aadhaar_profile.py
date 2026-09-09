"""
backend/tests/test_aadhaar_profile.py

Tests for Aadhaar Document Profile, Parser, and Validation.
"""
import pytest
from app.services.documents.profiles.document_profile import ProfileStatus
from app.services.documents.profiles.document_profile_registry import (
    document_profile_registry,
)
from app.services.documents.profiles.aadhaar_profile import AADHAAR_PROFILE
from app.services.documents.aadhaar.aadhaar_parser import parse_aadhaar
from app.services.documents.aadhaar.aadhaar_validator import validate_aadhaar_document
from app.schemas.ocr import TravelerFields
from app.services.ocr.ocr_engine import OCRRegion


class TestAadhaarProfile:
    def test_aadhaar_profile_configuration(self):
        profile = AADHAAR_PROFILE
        assert profile.document_type == "aadhaar"
        assert profile.display_name == "Aadhaar Card"
        assert profile.status == ProfileStatus.AVAILABLE
        assert profile.mrz_applicable is False
        assert profile.portrait_applicable is True
        assert profile.portrait_required is False
        assert "identity_number" in profile.field_schema
        assert "name" in profile.field_schema
        assert "name" in profile.required_fields

        for mod in ["ocr", "validation", "forensics", "biometrics", "registry", "risk"]:
            assert profile.is_module_supported(mod) is True

    def test_resolve_aadhaar_profile(self):
        profile = document_profile_registry.resolve("aadhaar")
        assert profile.document_type == "aadhaar"
        assert profile.status == ProfileStatus.AVAILABLE

    def test_resolve_aadhaar_aliases(self):
        for alias in ["aadhaar", "aadhaarcard", "aadhaarCard", "uid", "national_id", "nationalId", "nid"]:
            resolved = document_profile_registry.resolve(alias)
            assert resolved.document_type == "aadhaar"
            assert resolved.is_available() is True

    def test_parse_aadhaar_valid_regions(self):
        regions = [
            OCRRegion(text="GOVERNMENT OF INDIA", confidence=0.98, bbox=[[50, 20], [300, 20], [300, 40], [50, 40]]),
            OCRRegion(text="SNEHA PATEL", confidence=0.95, bbox=[[230, 110], [450, 110], [450, 130], [230, 130]]),
            OCRRegion(text="DOB: 18/09/1992", confidence=0.94, bbox=[[230, 160], [400, 160], [400, 180], [230, 180]]),
            OCRRegion(text="Female", confidence=0.92, bbox=[[230, 210], [320, 210], [320, 230], [230, 230]]),
            OCRRegion(text="8472 9103 8473", confidence=0.97, bbox=[[200, 390], [600, 390], [600, 430], [200, 430]]),
        ]
        parsed = parse_aadhaar(regions)
        assert parsed.identity_number.value == "847291038473"
        assert "SNEHA PATEL" in (parsed.name.value or "").upper()
        assert parsed.gender.value.upper() == "FEMALE"
        assert hasattr(parsed, "to_dict")
        d = parsed.to_dict()
        assert d["identity_number"] == "847291038473"

    def test_validate_aadhaar_document(self):
        # 847291038473 is a valid Verhoeff number
        traveler = TravelerFields(
            docNumber="8472 9103 8473",
            name="SNEHA PATEL",
            dob="18/09/1992",
            gender="Female",
        )
        val_res = validate_aadhaar_document(traveler)
        assert val_res["status"] in ("passed", "warning")

    def test_parse_aadhaar_card_bilingual_real_pattern(self):
        """Test extraction on real card-size bilingual Aadhaar with OCR artifacts (e.g. Bharath A)."""
        regions = [
            OCRRegion(text="ans", confidence=0.60),
            OCRRegion(text="Government of India", confidence=0.95),
            OCRRegion(text="Bharath A", confidence=0.96),
            OCRRegion(text="5/D0B:13/03/2007", confidence=0.89),
            OCRRegion(text="/MALE", confidence=0.98),
            OCRRegion(text="Csa am", confidence=0.55),
            OCRRegion(text="RCC", confidence=0.54),
            OCRRegion(text="Aadhaar is proof of identity,not of citizenship", confidence=0.96),
            OCRRegion(text="or date of birth.It should be used with verification online", confidence=0.94),
            OCRRegion(text="7697.66721283", confidence=0.96),
        ]
        parsed = parse_aadhaar(regions)
        assert parsed.identity_number.value == "769766721283"
        assert parsed.name.value == "BHARATH A"
        assert parsed.dob.value == "2007-03-13"
        assert parsed.gender.value == "MALE"
        assert parsed.issuing_authority.value == "Unique Identification Authority of India"

        traveler = TravelerFields(
            docNumber=parsed.identity_number.value,
            name=parsed.name.value,
            dob=parsed.dob.value,
            gender=parsed.gender.value,
            authority=parsed.issuing_authority.value,
        )
        val = validate_aadhaar_document(traveler)
        assert val["status"] == "passed"
        assert val["checks"]["required_fields"]["valid"] is True
        assert val["checks"]["identifier_checksum"]["valid"] is True

    def test_parse_aadhaar_long_letter_real_pattern(self):
        """Test extraction on real long letter e-Aadhaar with dual sections and address block (e.g. Sudha A)."""
        regions = [
            OCRRegion(text="Government of India", confidence=0.98),
            OCRRegion(text="Unigue Identification Authority of India", confidence=0.97),
            OCRRegion(text="Cs/EnrolmentNo2726/50651/05540", confidence=0.91),
            OCRRegion(text="To", confidence=0.96),
            OCRRegion(text="Sudha A", confidence=0.96),
            OCRRegion(text="W/O,Ashok,", confidence=0.93),
            OCRRegion(text="18/12,shirdi Ananda Flat,", confidence=0.94),
            OCRRegion(text="Mukunta Ramanujam Street,Madumanagar,", confidence=0.95),
            OCRRegion(text="Perambur,", confidence=0.94),
            OCRRegion(text="District: Chennai,", confidence=0.91),
            OCRRegion(text="PIN Code:600011.", confidence=0.91),
            OCRRegion(text="Your Aadhaar No.", confidence=0.85),
            OCRRegion(text="36634767 0846", confidence=0.96),
            OCRRegion(text="Government of India", confidence=0.95),
            OCRRegion(text="Sudha A", confidence=0.97),
            OCRRegion(text="DO01/01/1985", confidence=0.84),
            OCRRegion(text="Q/Female", confidence=0.88),
            OCRRegion(text="Aadhaar is proof of identitynot of citizenship", confidence=0.92),
            OCRRegion(text="or date of birth.t should be used with verification onine", confidence=0.93),
            OCRRegion(text="36634767 0846", confidence=0.97),
        ]
        parsed = parse_aadhaar(regions)
        assert parsed.identity_number.value == "366347670846"
        assert parsed.name.value == "SUDHA A"
        assert parsed.dob.value == "1985-01-01"
        assert parsed.gender.value == "FEMALE"
        assert parsed.address.value is not None
        assert "Perambur" in parsed.address.value
        assert "600011" in parsed.address.value

        traveler = TravelerFields(
            docNumber=parsed.identity_number.value,
            name=parsed.name.value,
            dob=parsed.dob.value,
            gender=parsed.gender.value,
            authority=parsed.issuing_authority.value,
            address=parsed.address.value,
        )
        val = validate_aadhaar_document(traveler)
        assert val["status"] == "passed"
        assert val["checks"]["required_fields"]["valid"] is True
        assert val["checks"]["identifier_checksum"]["valid"] is True


