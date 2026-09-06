"""
backend/tests/test_dl_profile.py

Tests for the Driving License Document Profile and registry integration.
"""
import pytest
from app.services.documents.profiles import document_profile_registry
from app.services.documents.profiles.document_profile import (
    DocumentType,
    ModuleSupportStatus,
    ProfileStatus,
)
from app.services.documents.profiles.driving_license_profile import DRIVING_LICENSE_PROFILE


class TestDrivingLicenseProfile:
    def test_profile_attributes(self):
        assert DRIVING_LICENSE_PROFILE.document_type == "driving_license"
        assert DRIVING_LICENSE_PROFILE.display_name == "Driving License"
        assert DRIVING_LICENSE_PROFILE.version == "0.9.0"
        assert DRIVING_LICENSE_PROFILE.status == ProfileStatus.AVAILABLE
        assert DRIVING_LICENSE_PROFILE.mrz_applicable is False
        assert DRIVING_LICENSE_PROFILE.portrait_applicable is True
        assert DRIVING_LICENSE_PROFILE.portrait_required is False

    def test_module_support(self):
        for mod in ["ocr", "validation", "forensics", "biometrics", "registry", "risk"]:
            assert DRIVING_LICENSE_PROFILE.is_module_supported(mod) is True
            assert DRIVING_LICENSE_PROFILE.modules[mod] == ModuleSupportStatus.SUPPORTED

    def test_required_and_field_schema(self):
        assert "name" in DRIVING_LICENSE_PROFILE.required_fields
        assert "docNumber" in DRIVING_LICENSE_PROFILE.required_fields
        assert "dob" in DRIVING_LICENSE_PROFILE.required_fields

        assert "blood_group" in DRIVING_LICENSE_PROFILE.field_schema
        assert "vehicle_classes" in DRIVING_LICENSE_PROFILE.field_schema
        assert "issuing_authority" in DRIVING_LICENSE_PROFILE.field_schema

    def test_registry_resolution_and_operational(self):
        profile = document_profile_registry.resolve("driving_license")
        assert profile is not None
        assert profile.document_type == "driving_license"
        assert profile.is_available() is True

        operational = document_profile_registry.resolve_operational("driving_license")
        assert operational.document_type == "driving_license"

    def test_registry_aliases(self):
        for alias in ["drivingLicense", "drivinglicense", "DRIVING_LICENSE"]:
            resolved = document_profile_registry.resolve(alias)
            assert resolved is not None
            assert resolved.document_type == "driving_license"
