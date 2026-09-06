"""
backend/app/services/documents/profiles/border_permit_profile.py

Border Permit Reference Profile.
Controlled reference profile targeting regional entry/border crossing permits.
NOTE: This is a controlled prototype reference profile and does NOT claim universal
support across all global or international border crossing permit formats.
"""
from app.services.documents.profiles.document_profile import (
    DocumentProfile,
    DocumentType,
    ModuleSupportStatus,
    ProfileStatus,
)

BORDER_PERMIT_PROFILE = DocumentProfile(
    document_type=DocumentType.BORDER_PERMIT.value,
    display_name="Border Permit",
    version="0.11.0",
    status=ProfileStatus.AVAILABLE,
    description="Border Permit Reference Profile supporting permit number, holder name, DOB, linked passport reference binding, validity period, permit type, border zone, and QR payload verification.",
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
        "permit_number": {"relative_x": 0.40, "relative_y": 0.12, "relative_w": 0.55, "relative_h": 0.12},
        "text_zone": {"relative_x": 0.35, "relative_y": 0.25, "relative_w": 0.60, "relative_h": 0.55},
        "qr_code": {"relative_x": 0.72, "relative_y": 0.55, "relative_w": 0.24, "relative_h": 0.38},
    },
    field_schema=[
        "docNumber",
        "permit_number",
        "name",
        "dob",
        "nationality",
        "passport_number",
        "valid_from",
        "valid_to",
        "permit_type",
        "border_zone",
        "port_of_entry",
        "issuing_authority",
        "qr_payload",
    ],
    required_fields=[
        "name",
        "docNumber",
        "validFrom",
        "validTo",
    ],
)
