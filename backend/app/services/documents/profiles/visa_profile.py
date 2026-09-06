"""
backend/app/services/documents/profiles/visa_profile.py

Visa Reference Profile.
Initial reference profile for visa screening and verification.
NOTE: This is an initial reference profile and does not claim universal visa support.
"""
from app.services.documents.profiles.document_profile import (
    DocumentProfile,
    DocumentType,
    ModuleSupportStatus,
    ProfileStatus,
)

VISA_PROFILE = DocumentProfile(
    document_type=DocumentType.VISA.value,
    display_name="Visa",
    version="0.7.0",
    status=ProfileStatus.AVAILABLE,
    description="Initial Visa Reference Profile supporting VIZ extraction, structural validation, and linked passport reference.",
    modules={
        "ocr": ModuleSupportStatus.SUPPORTED,
        "validation": ModuleSupportStatus.SUPPORTED,
        "forensics": ModuleSupportStatus.SUPPORTED,
        "biometrics": ModuleSupportStatus.SUPPORTED,
        "registry": ModuleSupportStatus.SUPPORTED,
        "risk": ModuleSupportStatus.SUPPORTED,
    },
    mrz_applicable=False,
    mrz_standard="Optional MRV",
    portrait_applicable=True,
    portrait_required=False,
    expected_regions={
        "photo": {"relative_x": 0.05, "relative_y": 0.15, "relative_w": 0.35, "relative_h": 0.45},
        "text_zone": {"relative_x": 0.40, "relative_y": 0.15, "relative_w": 0.55, "relative_h": 0.65},
        "background": {"relative_x": 0.68, "relative_y": 0.05, "relative_w": 0.26, "relative_h": 0.15},
    },
    field_schema=[
        "name",
        "docNumber",
        "passportNumber",
        "nationality",
        "dob",
        "visaType",
        "visaCategory",
        "issuedDate",
        "expiry",
        "entries",
        "durationOfStay",
        "authority",
    ],
    required_fields=[
        "name",
        "docNumber",
        "expiry",
    ],
)
