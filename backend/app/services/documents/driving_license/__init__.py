"""
backend/app/services/documents/driving_license/__init__.py

Driving License service package.
"""
from app.services.documents.driving_license.dl_field_normalizer import (
    COVItem,
    COVNormalizationResult,
    KNOWN_VEHICLE_CLASSES,
    NormalizationResult,
    NormalizationStatus,
    STATE_CODE_REGISTRY,
    StateCodeEntry,
    StateCodeStatus,
    VALID_BLOOD_GROUPS,
    extract_state_from_license_number,
    extract_state_info_from_license_number,
    normalize_blood_group,
    normalize_blood_group_detailed,
    normalize_dl_date,
    normalize_dl_date_detailed,
    normalize_dl_text,
    normalize_dl_text_detailed,
    normalize_license_number,
    normalize_license_number_detailed,
    normalize_state_code,
    normalize_vehicle_classes,
    normalize_vehicle_classes_detailed,
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
    "normalize_license_number_detailed",
    "normalize_dl_date",
    "normalize_dl_date_detailed",
    "normalize_dl_text",
    "normalize_dl_text_detailed",
    "normalize_blood_group",
    "normalize_blood_group_detailed",
    "normalize_vehicle_classes",
    "normalize_vehicle_classes_detailed",
    "extract_state_from_license_number",
    "extract_state_info_from_license_number",
    "normalize_state_code",
    "NormalizationStatus",
    "NormalizationResult",
    "COVItem",
    "COVNormalizationResult",
    "StateCodeStatus",
    "StateCodeEntry",
    "VALID_BLOOD_GROUPS",
    "KNOWN_VEHICLE_CLASSES",
    "STATE_CODE_REGISTRY",
]
