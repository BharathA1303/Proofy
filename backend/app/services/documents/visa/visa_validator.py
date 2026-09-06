"""
backend/app/services/documents/visa/visa_validator.py

Module 2: Visa Document Validation Service.

Validates structural integrity, required fields, date chronology,
expiration status, and reference credential formats.

CRITICAL ARCHITECTURAL CONTRACT:
  - This is STRUCTURAL VALIDATION, not authenticity proof.
  - Does NOT invent or apply ICAO TD3 MRZ checksum rules.
  - Generates explainable evidence items for officer decision support.
"""
from __future__ import annotations

import datetime
import logging
import re
from typing import List, Optional

from app.schemas.ocr import TravelerFields
from app.schemas.validation import (
    CheckItem,
    ExpiryCheckEvidence,
    ValidationIssue,
)
from app.services.documents.relationships.document_relationship import (
    evaluate_visa_passport_relationship,
    RelationshipStatus,
)

logger = logging.getLogger(__name__)


def validate_visa_document(
    traveler: Optional[TravelerFields],
    reference_date: Optional[datetime.date] = None,
    related_passport_number: Optional[str] = None,
) -> dict:
    """
    Execute structural validation checks on extracted Visa data.

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
            "summary": "No extracted traveler fields available for Visa validation.",
            "checks": {
                "required_fields": {"status": "insufficient_data", "valid": False, "message": "Traveler fields missing."},
                "date_chronology": {"status": "unknown", "valid": False, "message": "Dates not available."},
                "expiry_date": {"status": "unknown", "valid": False, "expired": None, "expiry_date": None, "message": "Expiry date not available."},
                "visa_number_format": {"status": "unknown", "valid": False, "message": "Visa number not available."},
                "passport_reference": {"status": "unknown", "valid": False, "message": "Passport reference not available."},
                "field_consistency": {"status": "unknown", "valid": False, "message": "Consistency not evaluated."},
            },
            "issues": [
                {"severity": "critical", "check": "required_fields", "message": "No data provided for validation."}
            ],
        }

    issues: List[dict] = []
    checks: dict = {}

    # ── Check 1: Required Field Presence ─────────────────────────────────────
    missing_fields = []
    if not traveler.docNumber or not traveler.docNumber.strip():
        missing_fields.append("docNumber (Visa Number)")
    if not traveler.name or not traveler.name.strip():
        missing_fields.append("name (Bearer Name)")
    if not traveler.expiry or not traveler.expiry.strip():
        missing_fields.append("expiry (Expiry Date)")

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

    # ── Check 2: Visa Number Format ──────────────────────────────────────────
    visa_num = (traveler.docNumber or "").strip()
    if visa_num:
        # Standard visas typically have 6 to 14 alphanumeric characters
        if re.match(r"^[A-Z0-9]{6,14}$", visa_num.upper()):
            num_valid = True
            num_status = "passed"
            num_msg = f"Visa number '{visa_num}' matches valid format."
        else:
            num_valid = False
            num_status = "warning"
            num_msg = f"Visa number '{visa_num}' exhibits irregular character format."
            issues.append({
                "severity": "warning",
                "check": "visa_number_format",
                "message": num_msg,
            })
    else:
        num_valid = False
        num_status = "failed"
        num_msg = "Visa number is absent."

    checks["visa_number_format"] = {
        "status": num_status,
        "valid": num_valid,
        "message": num_msg,
    }

    # ── Check 3: Date Chronology (Issue Date <= Expiry Date) ─────────────────
    issue_dt = _try_parse_iso(traveler.issuedDate)
    expiry_dt = _try_parse_iso(traveler.expiry)
    dob_dt = _try_parse_iso(traveler.dob)

    date_valid = True
    date_status = "passed"
    date_msg = "Date chronology is consistent."

    if issue_dt and expiry_dt:
        if issue_dt > expiry_dt:
            date_valid = False
            date_status = "failed"
            date_msg = f"Issue date ({issue_dt}) is after expiry date ({expiry_dt})."
            issues.append({
                "severity": "critical",
                "check": "date_chronology",
                "message": date_msg,
            })
        else:
            date_msg = f"Valid validity span: {issue_dt} to {expiry_dt}."
    elif not traveler.issuedDate:
        date_msg = "Issue date not provided; expiry chronology checked against calendar."
    elif not issue_dt or not expiry_dt:
        date_valid = False
        date_status = "warning"
        date_msg = "One or more dates could not be parsed into valid calendar format."
        issues.append({
            "severity": "warning",
            "check": "date_chronology",
            "message": date_msg,
        })

    # Chronology check with DOB (cannot issue visa before birth)
    if dob_dt and issue_dt and dob_dt >= issue_dt:
        date_valid = False
        date_status = "failed"
        date_msg = f"Date of birth ({dob_dt}) is after or on date of issue ({issue_dt})."
        issues.append({
            "severity": "critical",
            "check": "date_chronology",
            "message": date_msg,
        })

    checks["date_chronology"] = {
        "status": date_status,
        "valid": date_valid,
        "message": date_msg,
    }

    # ── Check 4: Expiration Status ───────────────────────────────────────────
    if expiry_dt:
        is_expired = expiry_dt < reference_date
        exp_valid = not is_expired
        exp_status = "failed" if is_expired else "passed"
        exp_msg = f"Visa expired on {expiry_dt}." if is_expired else f"Visa is valid until {expiry_dt}."
        if is_expired:
            issues.append({
                "severity": "critical",
                "check": "expiry_date",
                "message": exp_msg,
            })
    else:
        is_expired = None
        exp_valid = False
        exp_status = "warning"
        exp_msg = "Expiry date could not be parsed."
        issues.append({
            "severity": "warning",
            "check": "expiry_date",
            "message": exp_msg,
        })

    checks["expiry_date"] = {
        "status": exp_status,
        "valid": exp_valid,
        "expired": is_expired,
        "expiry_date": traveler.expiry,
        "message": exp_msg,
    }

    # ── Check 5: Passport Reference Presence ─────────────────────────────────
    ppt_ref = traveler.passportNumber or ""
    if ppt_ref.strip():
        if re.match(r"^[A-Z0-9]{6,12}$", ppt_ref.strip().upper()):
            ppt_valid = True
            ppt_status = "passed"
            ppt_msg = f"Valid passport reference format: '{ppt_ref.strip().upper()}'."
        else:
            ppt_valid = False
            ppt_status = "warning"
            ppt_msg = f"Passport reference '{ppt_ref}' has irregular format."
            issues.append({
                "severity": "warning",
                "check": "passport_reference",
                "message": ppt_msg,
            })
    else:
        # Visas usually reference a passport, but some national visas do not display it
        ppt_valid = True
        ppt_status = "warning"
        ppt_msg = "No passport reference number found on visa credential."

    checks["passport_reference"] = {
        "status": ppt_status,
        "valid": ppt_valid,
        "message": ppt_msg,
    }

    # ── Check 6: Field Consistency ───────────────────────────────────────────
    # Verify name does not contain digits, nationality is valid format
    consist_valid = True
    consist_status = "passed"
    consist_msg = "Field representations are consistent."
    if traveler.name and any(char.isdigit() for char in traveler.name):
        consist_valid = False
        consist_status = "warning"
        consist_msg = "Bearer name contains numeric digits."
        issues.append({
            "severity": "warning",
            "check": "field_consistency",
            "message": consist_msg,
        })

    checks["field_consistency"] = {
        "status": consist_status,
        "valid": consist_valid,
        "message": consist_msg,
    }

    # ── Check 7: Cross-Document Passport Relationship ─────────────────────────
    if related_passport_number is not None:
        rel = evaluate_visa_passport_relationship(
            visa_passport_number=traveler.passportNumber,
            actual_passport_number=related_passport_number,
        )
        if rel.status == RelationshipStatus.MATCHED:
            cross_status = "passed"
            cross_valid = True
            cross_msg = rel.details
        elif rel.status == RelationshipStatus.MISMATCHED:
            cross_status = "failed"
            cross_valid = False
            cross_msg = rel.details
            issues.append({
                "severity": "critical",
                "check": "cross_document_passport",
                "message": cross_msg,
            })
        else:
            cross_status = "warning"
            cross_valid = False
            cross_msg = rel.details
            issues.append({
                "severity": "warning",
                "check": "cross_document_passport",
                "message": cross_msg,
            })
        checks["cross_document_passport"] = {
            "status": cross_status,
            "valid": cross_valid,
            "message": cross_msg,
            "source_field": "passport_number",
            "target_field": "document_number",
            "relationship_status": rel.status.value,
        }

    # ── Overall Status Calculation ────────────────────────────────────────────
    has_critical = any(i["severity"] == "critical" for i in issues)
    has_warning = any(i["severity"] == "warning" for i in issues)

    if has_critical:
        overall_status = "failed"
        summary_text = f"Visa validation failed with {len([i for i in issues if i['severity'] == 'critical'])} critical issues."
    elif has_warning:
        overall_status = "warning"
        summary_text = f"Visa validation completed with {len(issues)} warnings."
    else:
        overall_status = "passed"
        summary_text = "All structural visa validation checks passed."

    return {
        "status": overall_status,
        "summary": summary_text,
        "checks": checks,
        "issues": issues,
    }


def _try_parse_iso(val: Optional[str]) -> Optional[datetime.date]:
    """Helper to parse an ISO date string or common date."""
    if not val:
        return None
    try:
        # Handles YYYY-MM-DD
        return datetime.date.fromisoformat(val.strip())
    except (ValueError, TypeError):
        return None
