"""
backend/app/services/documents/border_permit/border_permit_validator.py

Module 2: Border Permit Document Validation Service.
Focused on the Border Permit Reference Profile.

Validates:
1. Required field presence (permit number, holder name, validity dates).
2. Identifier format (canonical BP + 10 digits or recognized format).
3. Date validity and chronology (issue_date <= valid_from <= valid_to).
4. Expiration and temporal validity (ACTIVE, EXPIRED, NOT_YET_VALID).
5. Passport reference binding syntax.
6. Optional QR payload field consistency comparison.

CRITICAL RULES:
- EXPIRED is a document status condition; it is NOT evidence of forgery.
- Ambiguous identifiers produce warning issues, not automatic accusations of fraud.
- Zero demographic profiling: Nationality and border zone are never penalized as risk factors.
"""
from __future__ import annotations

import datetime
import logging
import re
from typing import Any, Dict, List, Optional

from app.schemas.ocr import TravelerFields
from app.services.documents.border_permit.border_permit_field_normalizer import (
    normalize_border_date,
    normalize_holder_name,
    normalize_permit_number,
)
from app.services.documents.border_permit.border_permit_qr_validator import (
    compare_ocr_and_border_permit_qr,
    parse_border_permit_qr_payload,
)

logger = logging.getLogger(__name__)


def validate_border_permit_document(
    traveler: Optional[TravelerFields],
    reference_date: Optional[datetime.date] = None,
) -> Dict[str, Any]:
    """
    Execute structural validation checks on extracted Border Permit data.

    Returns a dictionary matching DocumentValidationSummary structure:
      - status: 'passed' | 'warning' | 'failed' | 'insufficient_data'
      - summary: explanatory text
      - checks: dictionary of individual check items
      - issues: list of ValidationIssue items
    """
    if reference_date is None:
        reference_date = datetime.date.today()

    if not traveler:
        return {
            "status": "insufficient_data",
            "summary": "No extracted traveler fields available for Border Permit validation.",
            "checks": {
                "required_fields": {"status": "insufficient_data", "valid": False, "message": "Traveler fields missing."},
                "identifier_format": {"status": "unknown", "valid": False, "message": "Permit number not available."},
                "validity_period": {"status": "unknown", "valid": False, "message": "Validity dates not available."},
                "passport_binding": {"status": "unknown", "valid": False, "message": "Passport reference not available."},
                "qr_consistency": {"status": "not_applicable", "valid": True, "message": "QR payload absent."},
            },
            "issues": [
                {
                    "issue_type": "MISSING_TRAVELER_DATA",
                    "severity": "critical",
                    "description": "Traveler data structure is null or empty.",
                    "field": "traveler",
                }
            ],
        }

    checks: Dict[str, Any] = {}
    issues: List[Dict[str, Any]] = []

    # ── Check 1: Required Fields ─────────────────────────────────────────────
    permit_num_val = traveler.permitNumber or traveler.docNumber
    name_val = traveler.name
    valid_from_val = traveler.validFrom or traveler.issuedDate
    valid_to_val = traveler.validTo or traveler.expiry

    missing_fields = []
    if not permit_num_val:
        missing_fields.append("permitNumber")
    if not name_val:
        missing_fields.append("name")
    if not valid_from_val:
        missing_fields.append("validFrom")
    if not valid_to_val:
        missing_fields.append("validTo")

    if missing_fields:
        checks["required_fields"] = {
            "status": "failed",
            "valid": False,
            "missing": missing_fields,
            "message": f"Required fields missing: {', '.join(missing_fields)}",
        }
        issues.append({
            "issue_type": "REQUIRED_FIELDS_MISSING",
            "severity": "critical",
            "description": f"Mandatory Border Permit fields are absent: {', '.join(missing_fields)}.",
            "field": missing_fields[0],
        })
    else:
        checks["required_fields"] = {
            "status": "passed",
            "valid": True,
            "message": "All mandatory fields present.",
        }

    # ── Check 2: Permit Number Format & Ambiguity ────────────────────────────
    if permit_num_val:
        norm_num, is_ambig = normalize_permit_number(permit_num_val)
        if is_ambig:
            checks["identifier_format"] = {
                "status": "warning",
                "valid": False,
                "permit_number": norm_num,
                "message": "Ambiguous characters detected in permit number slot.",
            }
            issues.append({
                "issue_type": "AMBIGUOUS_IDENTIFIER",
                "severity": "warning",
                "description": f"Permit number '{permit_num_val}' contains ambiguous OCR characters.",
                "field": "permitNumber",
            })
        elif norm_num and (re.match(r"^BP\d{10}$", norm_num) or re.match(r"^BP\d{6,12}$", norm_num)):
            checks["identifier_format"] = {
                "status": "passed",
                "valid": True,
                "permit_number": norm_num,
                "message": "Permit number conforms to reference pattern.",
            }
        else:
            checks["identifier_format"] = {
                "status": "warning",
                "valid": False,
                "permit_number": norm_num,
                "message": f"Permit number '{permit_num_val}' does not conform to standard BP pattern.",
            }
            issues.append({
                "issue_type": "FORMAT_WARNING",
                "severity": "warning",
                "description": f"Permit number format '{permit_num_val}' does not strictly match canonical reference format.",
                "field": "permitNumber",
            })
    else:
        checks["identifier_format"] = {
            "status": "failed",
            "valid": False,
            "message": "Permit number is missing.",
        }

    # ── Check 3: Date Validity & Chronology ──────────────────────────────────
    parsed_from: Optional[datetime.date] = None
    parsed_to: Optional[datetime.date] = None

    if valid_from_val:
        iso_from = normalize_border_date(valid_from_val)
        if iso_from:
            try:
                parsed_from = datetime.date.fromisoformat(iso_from)
            except ValueError:
                pass

    if valid_to_val:
        iso_to = normalize_border_date(valid_to_val)
        if iso_to:
            try:
                parsed_to = datetime.date.fromisoformat(iso_to)
            except ValueError:
                pass

    if parsed_from and parsed_to:
        if parsed_from > parsed_to:
            checks["validity_period"] = {
                "status": "failed",
                "valid": False,
                "temporal_status": "INVALID_RANGE",
                "valid_from": parsed_from.isoformat(),
                "valid_to": parsed_to.isoformat(),
                "message": f"Inverted validity dates: Valid From ({parsed_from}) is after Valid To ({parsed_to}).",
            }
            issues.append({
                "issue_type": "INVALID_DATE_RANGE",
                "severity": "high",
                "description": f"Valid From date ({parsed_from}) cannot be after Valid To date ({parsed_to}).",
                "field": "validFrom",
            })
        elif parsed_to < reference_date:
            checks["validity_period"] = {
                "status": "warning",
                "valid": False,
                "temporal_status": "EXPIRED",
                "valid_from": parsed_from.isoformat(),
                "valid_to": parsed_to.isoformat(),
                "message": f"Border permit expired on {parsed_to}.",
            }
            issues.append({
                "issue_type": "DOCUMENT_EXPIRED",
                "severity": "medium",
                "description": f"Border permit expired on {parsed_to}.",
                "field": "validTo",
            })
        elif parsed_from > reference_date:
            checks["validity_period"] = {
                "status": "warning",
                "valid": False,
                "temporal_status": "NOT_YET_VALID",
                "valid_from": parsed_from.isoformat(),
                "valid_to": parsed_to.isoformat(),
                "message": f"Border permit is not yet valid (commences {parsed_from}).",
            }
            issues.append({
                "issue_type": "DOCUMENT_NOT_YET_VALID",
                "severity": "medium",
                "description": f"Border permit is not yet valid until {parsed_from}.",
                "field": "validFrom",
            })
        else:
            checks["validity_period"] = {
                "status": "passed",
                "valid": True,
                "temporal_status": "ACTIVE",
                "valid_from": parsed_from.isoformat(),
                "valid_to": parsed_to.isoformat(),
                "message": "Permit is currently within active validity window.",
            }
    elif valid_from_val or valid_to_val:
        checks["validity_period"] = {
            "status": "warning",
            "valid": False,
            "temporal_status": "INCOMPLETE_DATES",
            "message": "Validity dates could not be fully parsed into valid calendar dates.",
        }
        issues.append({
            "issue_type": "INVALID_DATE_FORMAT",
            "severity": "warning",
            "description": "One or more validity dates failed ISO calendar parsing.",
            "field": "validTo" if not parsed_to else "validFrom",
        })
    else:
        checks["validity_period"] = {
            "status": "failed",
            "valid": False,
            "temporal_status": "UNKNOWN",
            "message": "Validity dates are absent.",
        }

    # ── Check 4: Passport Reference Binding Syntax ───────────────────────────
    ppt_ref = traveler.passportNumber
    if ppt_ref:
        clean_ppt = ppt_ref.strip().upper()
        if re.match(r"^[A-Z0-9]{6,9}$", clean_ppt):
            checks["passport_binding"] = {
                "status": "passed",
                "valid": True,
                "passport_number": clean_ppt,
                "message": "Linked passport reference conforms to standard identifier syntax.",
            }
        else:
            checks["passport_binding"] = {
                "status": "warning",
                "valid": False,
                "passport_number": clean_ppt,
                "message": f"Linked passport reference '{clean_ppt}' does not conform to standard format.",
            }
            issues.append({
                "issue_type": "PASSPORT_SYNTAX_WARNING",
                "severity": "warning",
                "description": f"Linked passport number '{clean_ppt}' is non-standard.",
                "field": "passportNumber",
            })
    else:
        checks["passport_binding"] = {
            "status": "not_applicable",
            "valid": True,
            "message": "No linked passport number declared on permit.",
        }

    # ── Check 5: QR Code Consistency ─────────────────────────────────────────
    if traveler.qrPayload:
        qr_comp = compare_ocr_and_border_permit_qr(
            ocr_fields=traveler.model_dump(),
            qr_payload=traveler.qrPayload,
        )
        if qr_comp.get("status") == "MATCHED":
            checks["qr_consistency"] = {
                "status": "passed",
                "valid": True,
                "qr_status": qr_comp.get("qr_status"),
                "authentication": qr_comp.get("authentication"),
                "message": "QR payload decoded successfully; fields match visual OCR.",
            }
        elif qr_comp.get("status") == "MISMATCH":
            checks["qr_consistency"] = {
                "status": "failed",
                "valid": False,
                "qr_status": qr_comp.get("qr_status"),
                "authentication": qr_comp.get("authentication"),
                "inconsistencies": qr_comp.get("inconsistencies"),
                "message": "Discrepancy detected between QR payload and visual OCR text.",
            }
            issues.append({
                "issue_type": "QR_OCR_MISMATCH",
                "severity": "high",
                "description": f"QR payload conflicts with OCR: {'; '.join(qr_comp.get('inconsistencies', []))}",
                "field": "qrPayload",
            })
        else:
            checks["qr_consistency"] = {
                "status": "warning",
                "valid": False,
                "qr_status": qr_comp.get("qr_status"),
                "message": "QR payload present but could not be parsed.",
            }
    else:
        checks["qr_consistency"] = {
            "status": "not_applicable",
            "valid": True,
            "message": "No QR payload present on document.",
        }

    # ── Overall Status Rollup ────────────────────────────────────────────────
    has_critical = any(iss["severity"] == "critical" for iss in issues)
    has_high = any(iss["severity"] == "high" for iss in issues)
    has_warning = any(iss["severity"] in ("warning", "medium") for iss in issues)

    if has_critical or has_high:
        overall_status = "failed"
        summary = f"Border Permit validation failed with {len(issues)} issue(s)."
    elif has_warning:
        overall_status = "warning"
        summary = f"Border Permit validation passed with {len(issues)} warning(s)."
    else:
        overall_status = "passed"
        summary = "Border Permit passed all structural and temporal validation checks."

    return {
        "status": overall_status,
        "summary": summary,
        "checks": checks,
        "issues": issues,
    }
