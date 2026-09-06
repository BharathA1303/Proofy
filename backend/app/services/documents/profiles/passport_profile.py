"""
backend/app/services/documents/profiles/passport_profile.py

Passport Reference Profile.
Formalizes the reference implementation configuration for ICAO Doc 9303 TD3 passports.
"""
from app.services.documents.profiles.document_profile import (
    DocumentProfile,
    DocumentType,
    ModuleSupportStatus,
    ProfileStatus,
)

PASSPORT_PROFILE = DocumentProfile(
    document_type=DocumentType.PASSPORT.value,
    display_name="Passport",
    version="0.7.0",
    status=ProfileStatus.AVAILABLE,
    description="ICAO Doc 9303 compliant TD3 machine-readable travel document (Passport).",
    modules={
        "ocr": ModuleSupportStatus.SUPPORTED,
        "validation": ModuleSupportStatus.SUPPORTED,
        "forensics": ModuleSupportStatus.SUPPORTED,
        "biometrics": ModuleSupportStatus.SUPPORTED,
        "registry": ModuleSupportStatus.SUPPORTED,
        "risk": ModuleSupportStatus.SUPPORTED,
    },
    mrz_applicable=True,
    mrz_standard="TD3",
    portrait_applicable=True,
    portrait_required=True,
    expected_regions={
        "photo": {"relative_x": 0.05, "relative_y": 0.20, "relative_w": 0.35, "relative_h": 0.45},
        "mrz": {"relative_x": 0.05, "relative_y": 0.82, "relative_w": 0.90, "relative_h": 0.16},
        "background": {"relative_x": 0.68, "relative_y": 0.06, "relative_w": 0.26, "relative_h": 0.16},
    },
    field_schema=[
        "name",
        "docNumber",
        "dob",
        "nationality",
        "gender",
        "placeOfBirth",
        "authority",
        "issuedDate",
        "expiry",
        "mrz",
    ],
    required_fields=[
        "name",
        "docNumber",
        "dob",
        "nationality",
        "expiry",
    ],
)
