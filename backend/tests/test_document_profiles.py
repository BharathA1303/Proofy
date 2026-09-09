"""
tests/test_document_profiles.py

Tests for Document Profile Architecture and DocumentProfileRegistry.
Verifies profile registration, resolution, module capabilities,
unsupported document blocking, and metadata exposure.
"""
import pytest
from app.core.exceptions import UnknownDocumentTypeError, UnsupportedDocumentTypeError
from app.services.documents.profiles.document_profile import (
    DocumentProfile,
    DocumentType,
    ModuleSupportStatus,
    ProfileStatus,
)
from app.services.documents.profiles.document_profile_registry import (
    DocumentProfileRegistry,
    document_profile_registry,
)
from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


class TestDocumentProfileRegistry:
    def test_registry_contains_standard_profiles(self):
        """Registry must contain profiles for passport, visa, driving_license, aadhaar, voter_id, pan_card, border_permit."""
        profiles = document_profile_registry.get_all_profiles()
        types = {p.document_type for p in profiles}
        assert "passport" in types
        assert "visa" in types
        assert "driving_license" in types
        assert "aadhaar" in types
        assert "voter_id" in types
        assert "pan_card" in types
        assert "border_permit" in types


    def test_resolve_passport_profile(self):
        profile = document_profile_registry.resolve("passport")
        assert profile.document_type == "passport"
        assert profile.display_name == "Passport"
        assert profile.status == ProfileStatus.AVAILABLE
        assert profile.mrz_applicable is True
        assert profile.portrait_applicable is True
        assert profile.is_module_supported("ocr") is True
        assert profile.is_module_supported("risk") is True

    def test_resolve_visa_profile(self):
        profile = document_profile_registry.resolve("visa")
        assert profile.document_type == "visa"
        assert profile.display_name == "Visa"
        assert profile.status == ProfileStatus.AVAILABLE
        assert profile.mrz_applicable is False
        assert profile.portrait_applicable is True
        assert profile.is_module_supported("ocr") is True
        assert profile.is_module_supported("validation") is True
        assert profile.is_module_supported("registry") is True
        assert profile.is_module_supported("risk") is True

    def test_resolve_alias_normalization(self):
        """Aliases like 'drivingLicense' or 'DL' normalize properly."""
        profile_dl = document_profile_registry.resolve("drivingLicense")
        assert profile_dl.document_type == "driving_license"

        profile_nid = document_profile_registry.resolve("nationalId")
        assert profile_nid.document_type in ("aadhaar", "national_id")

        profile_voter = document_profile_registry.resolve("voterId")
        assert profile_voter.document_type == "voter_id"

        profile_pan = document_profile_registry.resolve("panCard")
        assert profile_pan.document_type == "pan_card"

        profile_bp = document_profile_registry.resolve("borderPermit")
        assert profile_bp.document_type == "border_permit"

    def test_resolve_unknown_document_type_raises(self):
        with pytest.raises(UnknownDocumentTypeError) as exc:
            document_profile_registry.resolve("alien_passport_xyz")
        assert "alien_passport_xyz" in str(exc.value)

    def test_resolve_operational_available(self):
        p_passport = document_profile_registry.resolve_operational("passport")
        assert p_passport.status == ProfileStatus.AVAILABLE

        p_visa = document_profile_registry.resolve_operational("visa")
        assert p_visa.status == ProfileStatus.AVAILABLE

        p_dl = document_profile_registry.resolve_operational("driving_license")
        assert p_dl.status == ProfileStatus.AVAILABLE

        p_aadhaar = document_profile_registry.resolve_operational("aadhaar")
        assert p_aadhaar.status == ProfileStatus.AVAILABLE

        p_voter = document_profile_registry.resolve_operational("voter_id")
        assert p_voter.status == ProfileStatus.AVAILABLE

        p_pan = document_profile_registry.resolve_operational("pan_card")
        assert p_pan.status == ProfileStatus.AVAILABLE

        p_nid = document_profile_registry.resolve_operational("national_id")
        assert p_nid.status == ProfileStatus.AVAILABLE

        p_bp = document_profile_registry.resolve_operational("border_permit")
        assert p_bp.status == ProfileStatus.AVAILABLE

    def test_resolve_operational_unsupported_raises(self):
        """Coming soon or unregistered documents cannot enter operational verification."""
        with pytest.raises(UnknownDocumentTypeError) as exc:
            document_profile_registry.resolve_operational("consular_id")
        assert "consular_id" in str(exc.value)

    def test_metadata_exposure(self):
        meta = document_profile_registry.get_all_profiles_metadata()
        assert len(meta) >= 7
        passport_meta = next(m for m in meta if m["type"] == "passport")
        assert passport_meta["status"] == "available"
        assert passport_meta["display_name"] == "Passport"

        visa_meta = next(m for m in meta if m["type"] == "visa")
        assert visa_meta["status"] == "available"
        assert visa_meta["display_name"] == "Visa"

        dl_meta = next(m for m in meta if m["type"] == "driving_license")
        assert dl_meta["status"] == "available"
        assert dl_meta["display_name"] == "Driving License"

        aadhaar_meta = next(m for m in meta if m["type"] == "aadhaar")
        assert aadhaar_meta["status"] == "available"
        assert aadhaar_meta["display_name"] == "Aadhaar Card"

        voter_meta = next(m for m in meta if m["type"] == "voter_id")
        assert voter_meta["status"] == "available"
        assert voter_meta["display_name"] == "Voter ID / EPIC"

        pan_meta = next(m for m in meta if m["type"] == "pan_card")
        assert pan_meta["status"] == "available"
        assert pan_meta["display_name"] == "PAN Card"

        bp_meta = next(m for m in meta if m["type"] == "border_permit")
        assert bp_meta["status"] == "available"
        assert bp_meta["display_name"] == "Border Permit"

    def test_api_profiles_endpoint(self):
        response = client.get("/api/v1/documents/profiles")
        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
        assert "total_count" in data
        docs = data["documents"]
        assert any(d["type"] == "passport" and d["status"] == "available" for d in docs)
        assert any(d["type"] == "visa" and d["status"] == "available" for d in docs)
        assert any(d["type"] == "driving_license" and d["status"] == "available" for d in docs)
        assert any(d["type"] == "aadhaar" and d["status"] == "available" for d in docs)
        assert any(d["type"] == "voter_id" and d["status"] == "available" for d in docs)
        assert any(d["type"] == "pan_card" and d["status"] == "available" for d in docs)
        assert any(d["type"] == "border_permit" and d["status"] == "available" for d in docs)

