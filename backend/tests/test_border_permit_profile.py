"""
backend/tests/test_border_permit_profile.py

Unit tests for BorderPermitProfile and DocumentProfileRegistry resolution.
Verifies module capabilities, required fields, version, and alias resolution.
"""
import pytest
from app.core.exceptions import UnknownDocumentTypeError
from app.services.documents.profiles.document_profile import (
    ModuleSupportStatus,
    ProfileStatus,
)
from app.services.documents.profiles.document_profile_registry import (
    document_profile_registry,
)


class TestBorderPermitProfile:
    def test_border_permit_profile_configuration(self):
        profile = document_profile_registry.resolve("border_permit")
        assert profile.document_type == "border_permit"
        assert profile.display_name == "Border Permit"
        assert profile.version == "0.11.0"
        assert profile.status == ProfileStatus.AVAILABLE
        assert profile.mrz_applicable is False
        assert profile.portrait_applicable is True

        # Module support checks
        assert profile.is_module_supported("ocr") is True
        assert profile.is_module_supported("validation") is True
        assert profile.is_module_supported("forensics") is True
        assert profile.is_module_supported("biometrics") is True
        assert profile.is_module_supported("registry") is True
        assert profile.is_module_supported("risk") is True

        # Required fields
        assert "name" in profile.required_fields
        assert "docNumber" in profile.required_fields
        assert "validFrom" in profile.required_fields
        assert "validTo" in profile.required_fields

        # Expected regions defined
        assert "photo" in profile.expected_regions
        assert "permit_number" in profile.expected_regions
        assert "text_zone" in profile.expected_regions
        assert "qr_code" in profile.expected_regions

    def test_resolve_border_permit_aliases(self):
        for alias in ["border_permit", "borderPermit", "borderpermit"]:
            resolved = document_profile_registry.resolve(alias)
            assert resolved.document_type == "border_permit"
            assert resolved.status == ProfileStatus.AVAILABLE

    def test_resolve_operational_border_permit(self):
        op = document_profile_registry.resolve_operational("border_permit")
        assert op is not None
        assert op.status == ProfileStatus.AVAILABLE

    def test_unknown_document_type_raises(self):
        with pytest.raises(UnknownDocumentTypeError):
            document_profile_registry.resolve("unknown_permit_xyz")
