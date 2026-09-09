"""
backend/app/services/documents/profiles/aadhaar_profile.py

Aadhaar Card Document Profile.
Indian identity document issued by UIDAI (Unique Identification Authority of India).
12-digit biometric identity number with Verhoeff D5 checksum, QR payload, and photo.

NOTE: Development prototype only. Does NOT connect to live UIDAI systems.
"""
from app.services.documents.profiles.document_profile import (
    DocumentProfile,
    DocumentType,
    ModuleSupportStatus,
    ProfileStatus,
)

AADHAAR_PROFILE = DocumentProfile(
    document_type=DocumentType.AADHAAR.value,
    display_name="Aadhaar Card",
    version="1.0.0",
    status=ProfileStatus.AVAILABLE,
    description=(
        "Indian Aadhaar identity card issued by UIDAI. "
        "Supports 12-digit identity number with Verhoeff checksum validation, "
        "full DOB/Year-of-Birth, gender, address, and QR payload verification. "
        "India prototype — does not connect to live UIDAI systems."
    ),
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
        "photo":           {"relative_x": 0.05, "relative_y": 0.25, "relative_w": 0.28, "relative_h": 0.45},
        "identity_number": {"relative_x": 0.20, "relative_y": 0.78, "relative_w": 0.60, "relative_h": 0.15},
        "text_zone":       {"relative_x": 0.35, "relative_y": 0.20, "relative_w": 0.60, "relative_h": 0.55},
        "qr_code":         {"relative_x": 0.70, "relative_y": 0.50, "relative_w": 0.25, "relative_h": 0.40},
    },
    field_schema=[
        "docNumber",
        "identity_number",
        "name",
        "dob",
        "year_of_birth",
        "gender",
        "address",
        "issuing_authority",
        "qr_payload",
    ],
    required_fields=[
        "name",
        "docNumber",
    ],
)
