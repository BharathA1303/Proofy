"""
backend/tests/test_national_id_profile.py

Tests for National ID Document Profile and Registration.
"""
import pytest
from app.core.exceptions import UnknownDocumentTypeError, UnsupportedDocumentTypeError
from app.services.documents.profiles.document_profile import (
    ModuleSupportStatus,
    ProfileStatus,
)
from app.services.documents.profiles.document_profile_registry import (
    document_profile_registry,
)
from app.services.documents.profiles.national_id_profile import NATIONAL_ID_PROFILE


class TestNationalIdProfile:
    def test_national_id_profile_configuration(self):
        profile = NATIONAL_ID_PROFILE
        assert profile.document_type == "national_id"
        assert profile.display_name == "National ID"
        assert profile.version == "0.10.0"
        assert profile.status == ProfileStatus.AVAILABLE
        assert profile.mrz_applicable is False
        assert profile.portrait_applicable is True
        assert profile.portrait_required is False
        assert "docNumber" in profile.field_schema
        assert "identity_number" in profile.field_schema
        assert "name" in profile.field_schema
        assert "name" in profile.required_fields
        assert "docNumber" in profile.required_fields

        # All 6 modules must be supported
        for mod in ["ocr", "validation", "forensics", "biometrics", "registry", "risk"]:
            assert profile.is_module_supported(mod) is True

    def test_resolve_national_id_profile(self):
        profile = document_profile_registry.resolve("national_id")
        assert profile.document_type == "national_id"
        assert profile.status == ProfileStatus.AVAILABLE

    def test_resolve_national_id_aliases(self):
        for alias in ["nationalId", "nationalid", "national_id", "nid", "aadhaar"]:
            resolved = document_profile_registry.resolve(alias)
            assert resolved.document_type == "national_id"
            assert resolved.is_available() is True

    def test_resolve_operational_national_id(self):
        operational = document_profile_registry.resolve_operational("national_id")
        assert operational.status == ProfileStatus.AVAILABLE
        assert operational.document_type == "national_id"
