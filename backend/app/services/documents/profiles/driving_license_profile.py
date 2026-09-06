"""
backend/app/services/documents/profiles/driving_license_profile.py

Driving License Reference Profile.
Initial reference profile targeting Indian Driving Licences (MoRTH / Sarathi format).
NOTE: This is an initial reference profile and does not claim universal Driving License support
across all global or state layouts.
"""
from app.services.documents.profiles.document_profile import (
    DocumentProfile,
    DocumentType,
    ModuleSupportStatus,
    ProfileStatus,
)

DRIVING_LICENSE_PROFILE = DocumentProfile(
    document_type=DocumentType.DRIVING_LICENSE.value,
    display_name="Driving License",
    version="0.9.0",
    status=ProfileStatus.AVAILABLE,
    description="Indian Driving Licence Reference Profile supporting field extraction, structural validation, and cross-document comparison.",
    modules={
        "ocr": ModuleSupportStatus.SUPPORTED,
        "validation": ModuleSupportStatus.SUPPORTED,
        "forensics": ModuleSupportStatus.SUPPORTED,
        "biometrics": ModuleSupportStatus.SUPPORTED,
        "registry": ModuleSupportStatus.SUPPORTED,
        "risk": ModuleSupportStatus.SUPPORTED,
    },
    mrz_applicable=False,
    mrz_standard=None,
    portrait_applicable=True,
    portrait_required=False,
    expected_regions={
        "photo": {"relative_x": 0.05, "relative_y": 0.20, "relative_w": 0.30, "relative_h": 0.50},
        "text_zone": {"relative_x": 0.38, "relative_y": 0.15, "relative_w": 0.58, "relative_h": 0.75},
        "background": {"relative_x": 0.05, "relative_y": 0.05, "relative_w": 0.90, "relative_h": 0.12},
    },
    field_schema=[
        "license_number",
        "docNumber",
        "name",
        "dob",
        "valid_from",
        "valid_to",
        "issuedDate",
        "expiry",
        "blood_group",
        "address",
        "vehicle_classes",
        "issuing_authority",
        "state",
    ],
    required_fields=[
        "name",
        "docNumber",
        "dob",
    ],
)
