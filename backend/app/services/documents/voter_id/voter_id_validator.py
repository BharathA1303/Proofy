"""
backend/app/services/documents/voter_id/voter_id_validator.py

Voter ID / EPIC Card Structural Validation Service.
Validates Election Commission of India EPIC cards.

Validates:
1. Required field presence (EPIC number, name).
2. EPIC number format (3 uppercase letters + 7 digits = 10 chars total).
3. DOB or age plausibility where available.
"""
from __future__ import annotations

import datetime
import logging
import re
from typing import Any, Dict, List, Optional

from app.schemas.ocr import TravelerFields
from app.services.documents.voter_id.voter_id_parser import normalize_epic_number

logger = logging.getLogger(__name__)

# EPIC number: exactly 3 letters + 7 digits
_EPIC_REGEX = re.compile(r"^[A-Z]{3}[0-9]{7}$")


def validate_voter_id_document(
    traveler: Optional[TravelerFields],
    reference_date: Optional[datetime.date] = None,
) -> Dict[str, Any]:
    """
    Execute structural validation checks on extracted Voter ID / EPIC card data.
    Returns a DocumentValidationSummary-compatible dict.
    """
    if reference_date is None:
        reference_date = datetime.date.today()

    if not traveler:
        return {
            "status": "insufficient_data",
            "summary": "No extracted traveler fields available for Voter ID validation.",
            "checks": {
                "required_fields":   {"status": "insufficient_data", "valid": False, "message": "Traveler fields missing."},
                "identifier_format": {"status": "unknown",           "valid": False, "message": "EPIC number not available."},
                "date_validity":     {"status": "unknown",           "valid": False, "message": "DOB or age not available."},
            },
            "issues": [{"severity": "critical", "check": "required_fields", "message": "No data provided for validation."}],
        }

    issues: List[Dict[str, Any]] = []
    checks: Dict[str, Any] = {}

    raw_id = (traveler.docNumber or "").strip()
    name   = (traveler.name or "").strip()
    dob    = (traveler.dob or "").strip()

    # ── Check 1: Required Fields ───────────────────────────────────────────────
    missing = []
    if not raw_id:
        missing.append("EPIC number")
    if not name:
        missing.append("name")

    if missing:
        req_valid  = False
        req_status = "failed"
        req_msg    = f"Missing required fields: {', '.join(missing)}."
        issues.append({"severity": "critical", "check": "required_fields", "message": req_msg})
    else:
        req_valid  = True
        req_status = "passed"
        req_msg    = "Required Voter ID fields are present."

    checks["required_fields"] = {"status": req_status, "valid": req_valid, "message": req_msg}

    # ── Check 2: EPIC Number Format ────────────────────────────────────────────
    norm_epic = normalize_epic_number(raw_id)
    if norm_epic and _EPIC_REGEX.match(norm_epic):
        id_fmt_valid  = True
        id_fmt_status = "passed"
        id_fmt_msg    = f"EPIC number format valid ({norm_epic[:3]}XXXXXXX)."
    elif raw_id:
        id_fmt_valid  = False
        id_fmt_status = "failed"
        id_fmt_msg    = f"EPIC number '{raw_id}' is invalid (expected format: 3 letters + 7 digits, e.g. ABC1234567)."
        issues.append({"severity": "critical", "check": "identifier_format", "message": id_fmt_msg})
    else:
        id_fmt_valid  = False
        id_fmt_status = "unknown"
        id_fmt_msg    = "EPIC number not provided."

    checks["identifier_format"] = {"status": id_fmt_status, "valid": id_fmt_valid, "message": id_fmt_msg}

    # ── Check 3: DOB Plausibility ──────────────────────────────────────────────
    if dob:
        # Try to extract year from dob string
        year_match = re.search(r"\b(19\d{2}|20[0-2]\d)\b", dob)
        if year_match:
            birth_year = int(year_match.group(1))
            if birth_year < 1900:
                date_valid, date_status = False, "warning"
                date_msg = f"Birth year ({birth_year}) is implausibly early."
                issues.append({"severity": "warning", "check": "date_validity", "message": date_msg})
            elif birth_year > reference_date.year:
                date_valid, date_status = False, "failed"
                date_msg = f"Birth year ({birth_year}) is in the future."
                issues.append({"severity": "critical", "check": "date_validity", "message": date_msg})
            else:
                date_valid, date_status = True, "passed"
                date_msg = f"Date of birth plausible (year: {birth_year})."
        else:
            date_valid, date_status = False, "warning"
            date_msg = "Could not parse birth year from DOB field."
            issues.append({"severity": "warning", "check": "date_validity", "message": date_msg})
    else:
        date_valid, date_status = False, "warning"
        date_msg = "Date of birth not available (optional for Voter ID)."
        # Only a warning, not critical — Voter ID may only have age printed

    checks["date_validity"] = {"status": date_status, "valid": date_valid, "message": date_msg}

    # ── Overall Status Synthesis ───────────────────────────────────────────────
    if any(i["severity"] == "critical" for i in issues):
        overall_status = "failed"
        summary = f"Voter ID validation failed: {issues[0]['message']}"
    elif any(i["severity"] in ("high", "warning") for i in issues):
        overall_status = "warning"
        summary = f"Voter ID validated with warnings: {issues[0]['message']}"
    elif not req_valid or not id_fmt_valid:
        overall_status = "failed"
        summary = "Voter ID failed structural validation checks."
    else:
        overall_status = "passed"
        summary = "All Voter ID / EPIC structural and format checks passed."

    return {"status": overall_status, "summary": summary, "checks": checks, "issues": issues}
