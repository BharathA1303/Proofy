"""
backend/app/services/registry/comparator.py

Registry field comparison engine.

Compares document identity fields against a registry record to produce:
  1. Per-field comparison results (RegistryFieldResult list)
  2. An overall RegistryStatus via deterministic decision tree

DECISION TREE (in priority order):
  IF provider unavailable         → UNAVAILABLE  (handled by engine, not here)
  ELSE IF timeout                 → TIMEOUT       (handled by engine, not here)
  ELSE IF provider error          → PROVIDER_ERROR (handled by engine)
  ELSE IF no record found         → NOT_FOUND
  ELSE IF registry says REVOKED   → REVOKED
  ELSE IF registry says SUSPENDED → SUSPENDED
  ELSE IF registry says EXPIRED   → EXPIRED (by registry_document_status)
  ELSE IF critical field mismatch → MISMATCH
  ELSE IF all critical fields OK  → MATCHED (or INCONCLUSIVE if partial data)
  ELSE                            → INCONCLUSIVE

CRITICAL FIELDS for Passport:
  - document_number   (highest priority — strict exact match)
  - date_of_birth     (critical identity anchor)
  - name              (critical — token-normalized, not fuzzy)
  - nationality       (critical)

SECONDARY FIELDS for Passport:
  - expiry_date       (secondary — mismatch noted but not critical failure alone)
  - issuing_authority (secondary — informational)
"""
from __future__ import annotations

import logging
from typing import List, Optional

from app.schemas.registry import (
    FieldMatchStatus,
    RegistryFieldResult,
    RegistryRecord,
    RegistryStatus,
    RegistryVerificationRequest,
)
from app.services.registry.normalizers import (
    dates_match,
    document_numbers_match,
    names_match,
    nationalities_match,
    normalize_authority,
    normalize_date,
    normalize_document_number,
    normalize_name,
    normalize_nationality,
)

logger = logging.getLogger(__name__)

# ── Critical field definitions per document type ────────────────────────────

CRITICAL_FIELDS: dict[str, list[str]] = {
    "passport": ["document_number", "date_of_birth", "name", "nationality"],
    "visa": ["document_number", "name", "nationality"],
    "driving_license": ["document_number", "date_of_birth", "name"],
    "national_id": ["document_number", "date_of_birth", "name"],
    "border_permit": ["document_number", "name"],
}

SECONDARY_FIELDS: dict[str, list[str]] = {
    "passport": ["expiry_date", "issuing_authority"],
    "visa": ["expiry_date", "issuing_authority"],
    "driving_license": ["expiry_date", "issuing_authority"],
    "national_id": ["issuing_authority"],
    "border_permit": ["expiry_date", "issuing_authority"],
}

# Registry document status values that override field comparison
_REGISTRY_REVOKED   = {"REVOKED"}
_REGISTRY_SUSPENDED = {"SUSPENDED"}
_REGISTRY_EXPIRED   = {"EXPIRED"}
_REGISTRY_INVALID   = {"INVALID"}
_REGISTRY_ACTIVE    = {"ACTIVE", "VALID"}


# ── Main comparison function ────────────────────────────────────────────────

def compare_fields(
    request: RegistryVerificationRequest,
    record: RegistryRecord,
) -> tuple[List[RegistryFieldResult], RegistryStatus]:
    """
    Compare all relevant identity fields between the verification request
    (document session data) and the registry record.

    Returns:
        (field_results, overall_status)
        field_results: Per-field evidence list
        overall_status: Deterministic RegistryStatus enum value
    """
    doc_type = request.document_type
    critical_fields = CRITICAL_FIELDS.get(doc_type, CRITICAL_FIELDS["passport"])
    secondary_fields = SECONDARY_FIELDS.get(doc_type, SECONDARY_FIELDS["passport"])

    results: List[RegistryFieldResult] = []

    # ── 1. Check registry-reported document status first ─────────────────
    reg_status = (record.registry_document_status or "").strip().upper()

    if reg_status in _REGISTRY_REVOKED:
        # Revocation overrides field comparison
        results.extend(_compare_all_fields(request, record, critical_fields, secondary_fields))
        logger.info("Registry reports document REVOKED for id=%s", request.verification_id)
        return results, RegistryStatus.REVOKED

    if reg_status in _REGISTRY_SUSPENDED:
        results.extend(_compare_all_fields(request, record, critical_fields, secondary_fields))
        logger.info("Registry reports document SUSPENDED for id=%s", request.verification_id)
        return results, RegistryStatus.SUSPENDED

    if reg_status in _REGISTRY_INVALID:
        results.extend(_compare_all_fields(request, record, critical_fields, secondary_fields))
        logger.info("Registry reports document INVALID for id=%s", request.verification_id)
        return results, RegistryStatus.INVALID

    # ── 2. Compare all fields ─────────────────────────────────────────────
    results.extend(_compare_all_fields(request, record, critical_fields, secondary_fields))

    # ── 3. Check registry-reported expiry (separate from field expiry_date) ─
    if reg_status in _REGISTRY_EXPIRED:
        logger.info("Registry reports document EXPIRED for id=%s", request.verification_id)
        return results, RegistryStatus.EXPIRED

    # ── 4. Check critical field mismatches ────────────────────────────────
    critical_results = [r for r in results if r.is_critical]

    critical_mismatches = [
        r for r in critical_results
        if r.status == FieldMatchStatus.MISMATCH
    ]
    critical_missing_in_both = [
        r for r in critical_results
        if r.status in (
            FieldMatchStatus.MISSING_IN_REGISTRY,
            FieldMatchStatus.MISSING_IN_DOCUMENT,
        )
    ]

    if critical_mismatches:
        logger.info(
            "Registry critical mismatch for id=%s on fields: %s",
            request.verification_id,
            [r.field for r in critical_mismatches],
        )
        return results, RegistryStatus.MISMATCH

    # ── 5. Check if enough critical data exists to declare MATCHED ────────
    matched_critical = [r for r in critical_results if r.status == FieldMatchStatus.MATCH]
    comparable_critical = [
        r for r in critical_results
        if r.status != FieldMatchStatus.NOT_COMPARED
    ]

    if not comparable_critical:
        # No comparable critical fields at all — cannot determine match
        return results, RegistryStatus.INCONCLUSIVE

    # If any critical fields missing on both sides, be conservative
    if len(critical_missing_in_both) >= len(critical_fields) // 2:
        return results, RegistryStatus.INCONCLUSIVE

    if len(matched_critical) == len(comparable_critical) and matched_critical:
        return results, RegistryStatus.MATCHED

    # Some critical fields matched, none mismatched — inconclusive
    return results, RegistryStatus.INCONCLUSIVE


def _compare_all_fields(
    request: RegistryVerificationRequest,
    record: RegistryRecord,
    critical_fields: list[str],
    secondary_fields: list[str],
) -> List[RegistryFieldResult]:
    """Build the full list of RegistryFieldResult for all relevant fields."""
    results: List[RegistryFieldResult] = []

    all_fields = [
        (f, True) for f in critical_fields
    ] + [
        (f, False) for f in secondary_fields
    ]

    for field_name, is_critical in all_fields:
        result = _compare_single_field(field_name, is_critical, request, record)
        if result is not None:
            results.append(result)

    return results


def _compare_single_field(
    field_name: str,
    is_critical: bool,
    request: RegistryVerificationRequest,
    record: RegistryRecord,
) -> Optional[RegistryFieldResult]:
    """Compare one field and return a RegistryFieldResult, or None if not applicable."""

    # Get document value (from request provenance)
    doc_provenance = _get_request_field(field_name, request)
    doc_raw = doc_provenance.value if doc_provenance else None

    # Get registry value (from record)
    reg_raw = _get_record_field(field_name, record)

    # Normalize both sides
    doc_normalized = _normalize_field(field_name, doc_raw)
    reg_normalized  = _normalize_field(field_name, reg_raw)

    # Determine match status
    if doc_raw is None and reg_raw is None:
        status = FieldMatchStatus.NOT_COMPARED
        note = "Field not available in document or registry"
    elif doc_raw is None:
        status = FieldMatchStatus.MISSING_IN_DOCUMENT
        note = "Field not extracted from document"
    elif reg_raw is None:
        status = FieldMatchStatus.MISSING_IN_REGISTRY
        note = "Field not present in registry record"
    else:
        matched = _fields_equal(field_name, doc_raw, reg_raw)
        status = FieldMatchStatus.MATCH if matched else FieldMatchStatus.MISMATCH
        note = None

    return RegistryFieldResult(
        field=field_name,
        document_value=doc_normalized,
        registry_value=reg_normalized,
        status=status,
        is_critical=is_critical,
        note=note,
    )


def _get_request_field(field_name: str, request: RegistryVerificationRequest):
    """Map field name to the request provenance object."""
    mapping = {
        "document_number": request.document_number,
        "date_of_birth": request.date_of_birth,
        "name": request.name,
        "nationality": request.nationality,
        "expiry_date": request.expiry_date,
        "issuing_authority": request.issuing_authority,
        "gender": request.gender,
    }
    return mapping.get(field_name)


def _get_record_field(field_name: str, record: RegistryRecord) -> Optional[str]:
    """Map field name to the registry record value."""
    mapping = {
        "document_number": record.document_number,
        "date_of_birth": record.date_of_birth,
        "name": record.name,
        "nationality": record.nationality,
        "expiry_date": record.expiry_date,
        "issuing_authority": record.issuing_authority,
        "gender": record.gender,
    }
    return mapping.get(field_name)


def _normalize_field(field_name: str, value: Optional[str]) -> Optional[str]:
    """Apply appropriate normalization for display purposes."""
    if value is None:
        return None
    if field_name == "document_number":
        return normalize_document_number(value)
    elif field_name in ("date_of_birth", "expiry_date"):
        return normalize_date(value) or value.strip().upper()
    elif field_name == "name":
        return normalize_name(value)
    elif field_name == "nationality":
        return normalize_nationality(value)
    elif field_name == "issuing_authority":
        return normalize_authority(value)
    else:
        return value.strip().upper()


def _fields_equal(field_name: str, doc_value: str, reg_value: str) -> bool:
    """Apply field-type-specific equality check."""
    if field_name == "document_number":
        # STRICT: no fuzzy matching
        return document_numbers_match(doc_value, reg_value)
    elif field_name in ("date_of_birth", "expiry_date"):
        return dates_match(doc_value, reg_value)
    elif field_name == "name":
        return names_match(doc_value, reg_value)
    elif field_name == "nationality":
        return nationalities_match(doc_value, reg_value)
    else:
        # Generic: normalized case-insensitive equality
        return (doc_value or "").strip().upper() == (reg_value or "").strip().upper()
