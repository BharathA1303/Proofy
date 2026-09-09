"""
backend/tests/test_pan_card_profile.py

Tests for PAN Card Profile, Parser, and Validation.
"""
import pytest
from app.services.documents.profiles.document_profile import ProfileStatus
from app.services.documents.profiles.document_profile_registry import (
    document_profile_registry,
)
from app.services.documents.profiles.pan_card_profile import PAN_CARD_PROFILE
from app.services.documents.pan_card.pan_card_parser import parse_pan_card
from app.services.documents.pan_card.pan_card_validator import validate_pan_card_document
from app.schemas.ocr import TravelerFields
from app.services.ocr.ocr_engine import OCRRegion


class TestPanCardProfile:
    def test_pan_card_profile_configuration(self):
        profile = PAN_CARD_PROFILE
        assert profile.document_type == "pan_card"
        assert profile.display_name == "PAN Card"
        assert profile.status == ProfileStatus.AVAILABLE
        assert profile.mrz_applicable is False
        assert profile.portrait_applicable is False
        assert profile.portrait_required is False
        assert "pan_number" in profile.field_schema
        assert "name" in profile.required_fields
        assert "docNumber" in profile.required_fields

        for mod in ["ocr", "validation", "forensics", "registry", "risk"]:
            assert profile.is_module_supported(mod) is True

    def test_resolve_pan_card_profile(self):
        profile = document_profile_registry.resolve("pan_card")
        assert profile.document_type == "pan_card"
        assert profile.status == ProfileStatus.AVAILABLE

    def test_resolve_pan_card_aliases(self):
        for alias in ["pan_card", "pancard", "panCard", "pan"]:
            resolved = document_profile_registry.resolve(alias)
            assert resolved.document_type == "pan_card"
            assert resolved.is_available() is True

    def test_parse_pan_card_valid_regions(self):
        regions = [
            OCRRegion(text="INCOME TAX DEPARTMENT", confidence=0.98, bbox=[[50, 20], [400, 20], [400, 40], [50, 40]]),
            OCRRegion(text="GOVT. OF INDIA", confidence=0.97, bbox=[[50, 45], [300, 45], [300, 65], [50, 65]]),
            OCRRegion(text="Permanent Account Number", confidence=0.95, bbox=[[50, 75], [350, 75], [350, 95], [50, 95]]),
            OCRRegion(text="AABCP1234C", confidence=0.97, bbox=[[50, 100], [250, 100], [250, 120], [50, 120]]),
            OCRRegion(text="Name: KAVITHA PRABHAKAR", confidence=0.95, bbox=[[50, 130], [350, 130], [350, 150], [50, 150]]),
            OCRRegion(text="Father's Name: PRABHAKAR", confidence=0.92, bbox=[[50, 160], [350, 160], [350, 180], [50, 180]]),
            OCRRegion(text="Date of Birth: 12/03/1988", confidence=0.94, bbox=[[50, 190], [350, 190], [350, 210], [50, 210]]),
        ]
        parsed = parse_pan_card(regions)
        assert parsed.pan_number.value == "AABCP1234C"
        assert "KAVITHA PRABHAKAR" in (parsed.name.value or "").upper()
        assert parsed.taxpayer_category == "Company"
        assert hasattr(parsed, "to_dict")
        d = parsed.to_dict()
        assert d["pan_number"] == "AABCP1234C"

    def test_validate_pan_card_document(self):
        traveler = TravelerFields(
            docNumber="AABCP1234C",
            name="KAVITHA PRABHAKAR",
            dob="12/03/1988",
        )
        val_res = validate_pan_card_document(traveler)
        assert val_res["status"] in ("passed", "warning")

