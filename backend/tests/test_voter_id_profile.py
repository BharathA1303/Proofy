"""
backend/tests/test_voter_id_profile.py

Tests for Voter ID / EPIC Profile, Parser, and Validation.
"""
import pytest
from app.services.documents.profiles.document_profile import ProfileStatus
from app.services.documents.profiles.document_profile_registry import (
    document_profile_registry,
)
from app.services.documents.profiles.voter_id_profile import VOTER_ID_PROFILE
from app.services.documents.voter_id.voter_id_parser import parse_voter_id
from app.services.documents.voter_id.voter_id_validator import validate_voter_id_document
from app.schemas.ocr import TravelerFields
from app.services.ocr.ocr_engine import OCRRegion


class TestVoterIdProfile:
    def test_voter_id_profile_configuration(self):
        profile = VOTER_ID_PROFILE
        assert profile.document_type == "voter_id"
        assert profile.display_name == "Voter ID / EPIC"
        assert profile.status == ProfileStatus.AVAILABLE
        assert profile.mrz_applicable is False
        assert profile.portrait_applicable is True
        assert "epic_number" in profile.field_schema
        assert "name" in profile.required_fields
        assert "docNumber" in profile.required_fields

        for mod in ["ocr", "validation", "forensics", "biometrics", "registry", "risk"]:
            assert profile.is_module_supported(mod) is True

    def test_resolve_voter_id_profile(self):
        profile = document_profile_registry.resolve("voter_id")
        assert profile.document_type == "voter_id"
        assert profile.status == ProfileStatus.AVAILABLE

    def test_resolve_voter_id_aliases(self):
        for alias in ["voter_id", "voterid", "voterId", "voterID", "epic", "voter"]:
            resolved = document_profile_registry.resolve(alias)
            assert resolved.document_type == "voter_id"
            assert resolved.is_available() is True

    def test_parse_voter_id_valid_regions(self):
        regions = [
            OCRRegion(text="ELECTION COMMISSION OF INDIA", confidence=0.98, bbox=[[50, 20], [400, 20], [400, 40], [50, 40]]),
            OCRRegion(text="ELECTORS PHOTO IDENTITY CARD", confidence=0.97, bbox=[[50, 45], [400, 45], [400, 65], [50, 65]]),
            OCRRegion(text="ABC1234567", confidence=0.96, bbox=[[50, 75], [200, 75], [200, 95], [50, 95]]),
            OCRRegion(text="Name: PRIYA KRISHNAMURTHY", confidence=0.95, bbox=[[200, 110], [450, 110], [450, 130], [200, 130]]),
            OCRRegion(text="Father's Name: KRISHNAMURTHY", confidence=0.92, bbox=[[200, 140], [450, 140], [450, 160], [200, 160]]),
            OCRRegion(text="Gender: Female", confidence=0.93, bbox=[[200, 170], [350, 170], [350, 190], [200, 190]]),
            OCRRegion(text="DOB: 15/04/1990", confidence=0.94, bbox=[[200, 200], [350, 200], [350, 220], [200, 220]]),
            OCRRegion(text="Constituency: Chennai Central", confidence=0.91, bbox=[[200, 230], [450, 230], [450, 250], [200, 250]]),
        ]
        parsed = parse_voter_id(regions)
        assert parsed.epic_number.value == "ABC1234567"
        assert "PRIYA KRISHNAMURTHY" in (parsed.name.value or "").upper()
        assert hasattr(parsed, "to_dict")
        d = parsed.to_dict()
        assert d["epic_number"] == "ABC1234567"

    def test_validate_voter_id_document(self):
        traveler = TravelerFields(
            docNumber="ABC1234567",
            name="PRIYA KRISHNAMURTHY",
            dob="15/04/1990",
            gender="Female",
        )
        val_res = validate_voter_id_document(traveler)
        assert val_res["status"] in ("passed", "warning")

