"""
backend/app/services/documents/profiles/pan_card_profile.py

PAN Card Document Profile.
Permanent Account Number card issued by the Income Tax Department of India.
PAN number format: 5 uppercase letters + 4 digits + 1 uppercase letter (e.g. ABCDE1234F).
The 4th letter encodes taxpayer category (P=person, C=company, etc.).
The 5th letter is the first letter of the surname.
No photograph on standard PAN cards.

NOTE: Development prototype only. Does NOT connect to live ITD/NSDL systems.
"""
from app.services.documents.profiles.document_profile import (
    DocumentProfile,
    DocumentType,
    ModuleSupportStatus,
    ProfileStatus,
)

PAN_CARD_PROFILE = DocumentProfile(
    document_type=DocumentType.PAN_CARD.value,
    display_name="PAN Card",
    version="1.0.0",
    status=ProfileStatus.AVAILABLE,
    description=(
        "Permanent Account Number (PAN) card issued by the Income Tax Department of India. "
        "10-character alphanumeric structure (AAAAA0000A). "
        "Supports PAN number, name, father's name, DOB, and issuing authority. "
        "India prototype — does not connect to live NSDL/UTIITSL systems."
    ),
    modules={
        "ocr": ModuleSupportStatus.SUPPORTED,
        "validation": ModuleSupportStatus.SUPPORTED,
        "forensics": ModuleSupportStatus.SUPPORTED,
        "biometrics": ModuleSupportStatus.NOT_SUPPORTED,   # PAN has no photo
        "registry": ModuleSupportStatus.SUPPORTED,
        "risk": ModuleSupportStatus.SUPPORTED,
    },
    mrz_applicable=False,
    mrz_standard=None,
    portrait_applicable=False,   # Standard PAN cards do not have photos
    portrait_required=False,
    expected_regions={
        "pan_number":  {"relative_x": 0.05, "relative_y": 0.55, "relative_w": 0.60, "relative_h": 0.10},
        "text_zone":   {"relative_x": 0.05, "relative_y": 0.30, "relative_w": 0.90, "relative_h": 0.50},
        "itd_logo":    {"relative_x": 0.05, "relative_y": 0.02, "relative_w": 0.30, "relative_h": 0.15},
    },
    field_schema=[
        "docNumber",
        "pan_number",
        "name",
        "father_name",
        "dob",
        "issuing_authority",
    ],
    required_fields=[
        "name",
        "docNumber",
    ],
)
