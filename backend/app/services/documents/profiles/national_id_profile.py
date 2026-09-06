"""
backend/app/services/documents/profiles/national_id_profile.py

National ID Reference Profile.
Controlled reference profile targeting the Indian National ID (UIDAI Aadhaar reference format).
NOTE: This is a controlled reference profile and does NOT claim universal National ID support
across all global or international card layouts.
"""
from app.services.documents.profiles.document_profile import (
    DocumentProfile,
    DocumentType,
    ModuleSupportStatus,
    ProfileStatus,
)

NATIONAL_ID_PROFILE = DocumentProfile(
    document_type=DocumentType.NATIONAL_ID.value,
    display_name="National ID",
    version="0.10.0",
    status=ProfileStatus.AVAILABLE,
    description="Indian National ID Reference Profile supporting 12-digit identity numbers with Verhoeff checksum, full DOB/YOB, gender, address, and QR payload verification.",
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
        "photo": {"relative_x": 0.05, "relative_y": 0.25, "relative_w": 0.28, "relative_h": 0.45},
        "identity_number": {"relative_x": 0.20, "relative_y": 0.78, "relative_w": 0.60, "relative_h": 0.15},
        "text_zone": {"relative_x": 0.35, "relative_y": 0.20, "relative_w": 0.60, "relative_h": 0.55},
        "qr_code": {"relative_x": 0.70, "relative_y": 0.50, "relative_w": 0.25, "relative_h": 0.40},
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
