"""
backend/app/services/documents/profiles/voter_id_profile.py

Voter ID / EPIC Document Profile.
Indian Electors Photo Identity Card issued by the Election Commission of India.
EPIC number format: 3 uppercase letters + 7 digits (e.g. ABC1234567).

NOTE: Development prototype only. Does NOT connect to live ECI systems.
"""
from app.services.documents.profiles.document_profile import (
    DocumentProfile,
    DocumentType,
    ModuleSupportStatus,
    ProfileStatus,
)

VOTER_ID_PROFILE = DocumentProfile(
    document_type=DocumentType.VOTER_ID.value,
    display_name="Voter ID / EPIC",
    version="1.0.0",
    status=ProfileStatus.AVAILABLE,
    description=(
        "Indian Electors Photo Identity Card (EPIC) issued by the Election Commission of India. "
        "Supports EPIC number (3-letter + 7-digit format), name, father's name, DOB/age, "
        "constituency, part number, serial number, and gender. "
        "India prototype — does not connect to live ECI voter roll systems."
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
        "photo":       {"relative_x": 0.55, "relative_y": 0.10, "relative_w": 0.38, "relative_h": 0.45},
        "epic_number": {"relative_x": 0.05, "relative_y": 0.65, "relative_w": 0.90, "relative_h": 0.12},
        "text_zone":   {"relative_x": 0.05, "relative_y": 0.12, "relative_w": 0.48, "relative_h": 0.50},
        "eci_logo":    {"relative_x": 0.38, "relative_y": 0.00, "relative_w": 0.24, "relative_h": 0.12},
    },
    field_schema=[
        "docNumber",
        "epic_number",
        "name",
        "father_name",
        "dob",
        "gender",
        "constituency",
        "part_number",
        "serial_number",
        "issuing_authority",
    ],
    required_fields=[
        "name",
        "docNumber",
    ],
)
