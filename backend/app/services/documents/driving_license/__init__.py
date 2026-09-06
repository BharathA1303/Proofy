"""
backend/app/services/documents/driving_license/__init__.py

Driving License service package.
"""
from app.services.documents.driving_license.dl_field_normalizer import (
    extract_state_from_license_number,
    normalize_blood_group,
    normalize_dl_date,
    normalize_dl_text,
    normalize_license_number,
    normalize_vehicle_classes,
)
from app.services.documents.driving_license.dl_parser import (
    DLField,
    ParsedDrivingLicenseData,
    parse_driving_license,
)

__all__ = [
    "DLField",
    "ParsedDrivingLicenseData",
    "parse_driving_license",
    "normalize_license_number",
    "normalize_dl_date",
    "normalize_dl_text",
    "normalize_blood_group",
    "normalize_vehicle_classes",
    "extract_state_from_license_number",
]
