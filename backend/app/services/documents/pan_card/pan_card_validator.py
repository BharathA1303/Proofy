"""
backend/app/services/documents/pan_card/pan_card_validator.py

PAN Card Structural Validation Service.
Validates Income Tax Department PAN cards using document-specific rules.

Validates:
1. Required field presence (PAN number, name).
2. PAN number format: AAAAA0000A (5 uppercase letters + 4 digits + 1 uppercase letter).
3. Taxpayer category decoding (4th character).
4. DOB plausibility (where available).
"""
from __future__ import annotations

import datetime
import logging
import re
from typing import Any, Dict, List, Optional

from app.schemas.ocr import TravelerFields
from app.services.documents.pan_card.pan_card_parser import (
    decode_pan_category,
    normalize_pan_number,
    PAN_PATTERN,
)

logger = logging.getLogger(__name__)


def validate_pan_card_document(
    traveler: Optional[TravelerFields],
    reference_date: Optional[datetime.date] = None,
) -> Dict[str, Any]:
    """
    Execute structural validation checks on extracted PAN Card data.
    Returns a DocumentValidationSummary-compatible dict.
    """
    if reference_date is None:
        reference_date = datetime.date.today()

    if not traveler:
        return {
            "status": "insufficient_data",
            "summary": "No extracted traveler fields available for PAN Card validation.",
            "checks": {
                "required_fields":   {"status": "insufficient_data", "valid": False, "message": "Traveler fields missing."},
                "identifier_format": {"status": "unknown",           "valid": False, "message": "PAN number not available."},
                "date_validity":     {"status": "not_applicable",    "valid": True,  "message": "DOB not required for PAN."},
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
        missing.append("PAN number")
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
        req_msg    = "Required PAN Card fields are present."

    checks["required_fields"] = {"status": req_status, "valid": req_valid, "message": req_msg}

    # ── Check 2: PAN Number Format ─────────────────────────────────────────────
    norm_pan = normalize_pan_number(raw_id)
    if norm_pan and PAN_PATTERN.match(norm_pan):
        category = decode_pan_category(norm_pan)
        id_fmt_valid  = True
        id_fmt_status = "passed"
        id_fmt_msg    = f"PAN number format valid ({norm_pan[:3]}XXXXXXX). Taxpayer category: {category}."
    elif raw_id:
        id_fmt_valid  = False
        id_fmt_status = "failed"
        id_fmt_msg    = f"PAN number '{raw_id}' is invalid (expected format: AAAAA0000A — 5 letters, 4 digits, 1 letter)."
        issues.append({"severity": "critical", "check": "identifier_format", "message": id_fmt_msg})
    else:
        id_fmt_valid  = False
        id_fmt_status = "unknown"
        id_fmt_msg    = "PAN number not provided."

    checks["identifier_format"] = {"status": id_fmt_status, "valid": id_fmt_valid, "message": id_fmt_msg}

    # ── Check 3: DOB Plausibility (optional for PAN) ───────────────────────────
    if dob:
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
    else:
        # DOB is optional on PAN — not a failure
        date_valid, date_status = True, "not_applicable"
        date_msg = "Date of birth field not present (not required on PAN Card)."

    checks["date_validity"] = {"status": date_status, "valid": date_valid, "message": date_msg}

    # ── Overall Status Synthesis ───────────────────────────────────────────────
    if any(i["severity"] == "critical" for i in issues):
        overall_status = "failed"
        summary = f"PAN Card validation failed: {issues[0]['message']}"
    elif any(i["severity"] in ("high", "warning") for i in issues):
        overall_status = "warning"
        summary = f"PAN Card validated with warnings: {issues[0]['message']}"
    elif not req_valid or not id_fmt_valid:
        overall_status = "failed"
        summary = "PAN Card failed structural validation checks."
    else:
        overall_status = "passed"
        summary = "All PAN Card structural and format checks passed."

    return {"status": overall_status, "summary": summary, "checks": checks, "issues": issues}
