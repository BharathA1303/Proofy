"""
backend/app/services/documents/driving_license/dl_validator.py

Module 2: Driving License Document Validation Service.

Validates structural integrity, required fields, identifier format,
date chronology, age eligibility, and expiration status.

CRITICAL ARCHITECTURAL CONTRACT:
  - This is STRUCTURAL VALIDATION, not an authenticity proof.
  - Generates explainable evidence items for officer decision support.
  - A syntactically unusual identifier generates a FORMAT_WARNING,
    never a "FORGED_DOCUMENT" declaration.
"""
from __future__ import annotations

import datetime
import logging
import re
from typing import Any, Dict, List, Optional

from app.schemas.ocr import TravelerFields
from app.services.documents.driving_license.dl_field_normalizer import (
    _INDIAN_STATE_CODES,
    normalize_dl_date,
    normalize_license_number,
)

logger = logging.getLogger(__name__)


def validate_driving_license_document(
    traveler: Optional[TravelerFields],
    reference_date: Optional[datetime.date] = None,
) -> Dict[str, Any]:
    """
    Execute structural validation checks on extracted Driving License data.

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
            "summary": "No extracted traveler fields available for Driving License validation.",
            "checks": {
                "required_fields": {"status": "insufficient_data", "valid": False, "message": "Traveler fields missing."},
                "license_number_format": {"status": "unknown", "valid": False, "message": "License number not available."},
                "date_chronology": {"status": "unknown", "valid": False, "message": "Dates not available."},
                "expiry_date": {"status": "unknown", "valid": False, "expired": None, "expiry_date": None, "message": "Expiry date not available."},
                "age_eligibility": {"status": "unknown", "valid": False, "message": "DOB or issue date not available."},
            },
            "issues": [
                {"severity": "critical", "check": "required_fields", "message": "No data provided for validation."}
            ],
        }

    issues: List[Dict[str, Any]] = []
    checks: Dict[str, Any] = {}

    # ── Check 1: Required Field Presence ─────────────────────────────────────
    missing_fields = []
    doc_num = (traveler.docNumber or "").strip()
    name = (traveler.name or "").strip()
    dob_str = (traveler.dob or "").strip()

    if not doc_num:
        missing_fields.append("docNumber (License Number)")
    if not name:
        missing_fields.append("name (Bearer Name)")
    if not dob_str:
        missing_fields.append("dob (Date of Birth)")

    if missing_fields:
        req_valid = False
        req_status = "failed" if len(missing_fields) > 1 else "warning"
        req_msg = f"Missing required fields: {', '.join(missing_fields)}."
        issues.append({
            "severity": "critical" if req_status == "failed" else "warning",
            "check": "required_fields",
            "message": req_msg,
        })
    else:
        req_valid = True
        req_status = "passed"
        req_msg = "All primary required fields are present."

    checks["required_fields"] = {
        "status": req_status,
        "valid": req_valid,
        "message": req_msg,
    }

    # ── Check 2: License Number Format ───────────────────────────────────────
    norm_num = normalize_license_number(doc_num)
    if norm_num:
        # Standard Indian MoRTH DL format: SS-RR-YYYY-NNNNNNN (15 or 16 chars)
        # Legacy Indian format: SS-RR-YYYYNNNNNNN or SS-RR-NNNNNNN
        is_canonical_indian = bool(re.match(r"^[A-Z]{2}\d{2}(?:19|20)\d{2}\d{7}$", norm_num))
        is_legacy_indian = bool(re.match(r"^[A-Z]{2}\d{2}\d{7,11}$", norm_num))

        if is_canonical_indian:
            num_valid = True
            num_status = "passed"
            num_msg = f"License number '{norm_num}' conforms to canonical MoRTH standard."
        elif is_legacy_indian:
            num_valid = True
            num_status = "passed"
            num_msg = f"License number '{norm_num}' matches recognized legacy state DL format."
        else:
            num_valid = False
            num_status = "warning"
            num_msg = f"The extracted identifier '{norm_num}' does not confidently match the supported reference profile."
            issues.append({
                "severity": "warning",
                "check": "license_number_format",
                "message": num_msg,
            })
    else:
        num_valid = False
        num_status = "failed"
        num_msg = "License number is absent or unparseable."
        issues.append({
            "severity": "critical",
            "check": "license_number_format",
            "message": num_msg,
        })

    checks["license_number_format"] = {
        "status": num_status,
        "valid": num_valid,
        "message": num_msg,
    }

    # ── Check 3: Date Chronology & Validity ──────────────────────────────────
    parsed_dob = _parse_date(dob_str)
    parsed_issue = _parse_date(traveler.issuedDate)
    parsed_expiry = _parse_date(traveler.expiry)

    chrono_valid = True
    chrono_status = "passed"
    chrono_msg = "Dates are logically consistent."

    if parsed_issue and parsed_expiry:
        if parsed_issue > parsed_expiry:
            chrono_valid = False
            chrono_status = "failed"
            chrono_msg = f"Inverted validity: issue date ({parsed_issue}) is after expiry date ({parsed_expiry})."
            issues.append({
                "severity": "critical",
                "check": "date_chronology",
                "message": chrono_msg,
            })
        else:
            chrono_msg = f"Valid from {parsed_issue} to {parsed_expiry}."
    elif not parsed_issue and not parsed_expiry:
        chrono_status = "unknown"
        chrono_msg = "Validity dates not available for chronology check."

    checks["date_chronology"] = {
        "status": chrono_status,
        "valid": chrono_valid,
        "message": chrono_msg,
    }

    # ── Check 4: Age Eligibility (at least 18 at issue date / today) ────────
    age_valid = True
    age_status = "passed"
    age_msg = "Holder age is valid."

    if parsed_dob:
        calc_reference = parsed_issue or reference_date
        age_years = (calc_reference - parsed_dob).days / 365.25
        if age_years < 18.0:
            age_valid = False
            age_status = "failed"
            age_msg = f"Underage driver: age at reference/issue date is {age_years:.1f} years (minimum 18 required)."
            issues.append({
                "severity": "critical",
                "check": "age_eligibility",
                "message": age_msg,
            })
        elif age_years > 110.0:
            age_valid = False
            age_status = "warning"
            age_msg = f"Date of birth indicates implausible age ({age_years:.1f} years)."
            issues.append({
                "severity": "warning",
                "check": "age_eligibility",
                "message": age_msg,
            })
        else:
            age_msg = f"Holder age verified ({int(age_years)} years)."
    else:
        age_status = "unknown"
        age_valid = False
        age_msg = "Date of birth not available for age verification."

    checks["age_eligibility"] = {
        "status": age_status,
        "valid": age_valid,
        "message": age_msg,
    }

    # ── Check 5: Expiration Status ───────────────────────────────────────────
    if parsed_expiry:
        is_expired = parsed_expiry < reference_date
        exp_valid = not is_expired
        exp_status = "failed" if is_expired else "passed"
        exp_msg = f"Driving license expired on {parsed_expiry}." if is_expired else f"License is active (expires {parsed_expiry})."
        if is_expired:
            issues.append({
                "severity": "critical",
                "check": "expiry_date",
                "message": exp_msg,
            })
    else:
        is_expired = None
        exp_valid = True
        exp_status = "unknown"
        exp_msg = "Expiry date not available."

    checks["expiry_date"] = {
        "status": exp_status,
        "valid": exp_valid,
        "expired": is_expired,
        "expiry_date": parsed_expiry.isoformat() if parsed_expiry else None,
        "message": exp_msg,
    }

    # ── Overall Status Synthesis ─────────────────────────────────────────────
    if any(issue["severity"] == "critical" for issue in issues):
        overall_status = "failed"
        summary = f"Driving License validation failed: {issues[0]['message']}"
    elif any(issue["severity"] == "warning" for issue in issues):
        overall_status = "warning"
        summary = f"Driving License validated with warnings: {issues[0]['message']}"
    elif not req_valid or not num_valid:
        overall_status = "failed"
        summary = "Driving License failed primary structural validation checks."
    else:
        overall_status = "passed"
        summary = "All Driving License structural and chronology checks passed."

    return {
        "status": overall_status,
        "summary": summary,
        "checks": checks,
        "issues": issues,
    }


def _parse_date(date_str: Optional[str]) -> Optional[datetime.date]:
    """Safely parse a date string into datetime.date."""
    if not date_str:
        return None
    iso_date = normalize_dl_date(date_str)
    if not iso_date:
        return None
    try:
        parts = [int(p) for p in iso_date.split("-")]
        return datetime.date(parts[0], parts[1], parts[2])
    except (ValueError, IndexError):
        return None
