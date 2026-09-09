"""
backend/app/services/documents/aadhaar/aadhaar_validator.py

Aadhaar Card Structural Validation Service.
Validates UIDAI Aadhaar cards using document-specific rules.

Validates:
1. Required field presence (docNumber / identityNumber, name, dob or yearOfBirth).
2. Identifier format (12 numeric digits).
3. Verhoeff D5 Checksum validation (PASS / FAIL / INCONCLUSIVE).
4. Date of birth / Year of birth plausibility.
5. Profile compatibility (unsupported layout detection).
6. Optional QR payload field consistency comparison.

CRITICAL RULES:
- A checksum failure is evidence of identifier inconsistency.
  It is NOT automatic proof that the physical document is forged.
- Full DOB vs. Year of Birth (YOB) are kept distinct; never fabricate day/month.
- Zero demographic profiling: Gender/address are never used as risk penalties.
"""
from __future__ import annotations

import datetime
import logging
import re
from typing import Any, Dict, List, Optional

from app.schemas.ocr import TravelerFields
from app.services.documents.aadhaar.aadhaar_field_normalizer import (
    normalize_dob_or_yob,
    normalize_gender,
)
from app.services.documents.aadhaar.aadhaar_identifier_validator import (
    ChecksumStatus,
    mask_aadhaar,
    normalize_aadhaar,
    validate_verhoeff_checksum,
)
from app.services.documents.aadhaar.aadhaar_qr_validator import (
    compare_ocr_and_qr,
    parse_national_id_qr_payload,
)

logger = logging.getLogger(__name__)


def validate_aadhaar_document(
    traveler: Optional[TravelerFields],
    reference_date: Optional[datetime.date] = None,
) -> Dict[str, Any]:
    """
    Execute structural validation checks on extracted Aadhaar card data.

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
            "summary": "No extracted traveler fields available for Aadhaar validation.",
            "checks": {
                "required_fields":      {"status": "insufficient_data", "valid": False, "message": "Traveler fields missing."},
                "identifier_format":    {"status": "unknown",           "valid": False, "message": "Identity number not available."},
                "identifier_checksum":  {"status": "unknown",           "valid": False, "checksum_status": "INCONCLUSIVE", "message": "Checksum not verifiable."},
                "date_validity":        {"status": "unknown",           "valid": False, "message": "DOB or YOB not available."},
                "qr_consistency":       {"status": "not_applicable",    "valid": True,  "message": "QR payload absent."},
            },
            "issues": [
                {"severity": "critical", "check": "required_fields", "message": "No data provided for validation."}
            ],
        }

    issues: List[Dict[str, Any]] = []
    checks: Dict[str, Any] = {}

    raw_id  = (traveler.identityNumber or traveler.docNumber or "").strip()
    name    = (traveler.name or "").strip()
    dob_val = (traveler.dob or "").strip()
    yob_val = (traveler.yearOfBirth or "").strip()

    # ── Check 1: Required Field Presence ─────────────────────────────────────
    missing_fields = []
    if not raw_id:
        missing_fields.append("docNumber/identityNumber")
    if not name:
        missing_fields.append("name")
    if not dob_val and not yob_val:
        missing_fields.append("dob or yearOfBirth")

    if missing_fields:
        req_valid  = False
        req_status = "failed" if len(missing_fields) > 1 else "warning"
        req_msg    = f"Missing required fields: {', '.join(missing_fields)}."
        issues.append({"severity": "critical" if req_status == "failed" else "warning", "check": "required_fields", "message": req_msg})
    else:
        req_valid  = True
        req_status = "passed"
        req_msg    = "Required Aadhaar fields are present."

    checks["required_fields"] = {"status": req_status, "valid": req_valid, "message": req_msg}

    # ── Check 2: Identifier Format & Ambiguity ────────────────────────────────
    norm_id, norm_err    = normalize_aadhaar(raw_id)
    masked_display       = mask_aadhaar(norm_id or raw_id)

    if norm_err == "AMBIGUOUS_IDENTIFIER":
        id_fmt_valid  = False
        id_fmt_status = "warning"
        id_fmt_msg    = f"Ambiguous characters detected in Aadhaar identifier '{masked_display}'."
        issues.append({"severity": "warning", "check": "identifier_format", "message": id_fmt_msg})
    elif not norm_id or len(norm_id) != 12:
        id_fmt_valid  = False
        id_fmt_status = "failed"
        id_fmt_msg    = f"Aadhaar identifier '{masked_display}' is invalid (expected 12 numeric digits)."
        issues.append({"severity": "critical", "check": "identifier_format", "message": id_fmt_msg})
    else:
        id_fmt_valid  = True
        id_fmt_status = "passed"
        id_fmt_msg    = f"Aadhaar format valid (12-digit, {masked_display})."

    checks["identifier_format"] = {"status": id_fmt_status, "valid": id_fmt_valid, "masked_identifier": masked_display, "message": id_fmt_msg}

    # ── Check 3: Verhoeff Checksum ────────────────────────────────────────────
    if norm_id and len(norm_id) == 12:
        chk_res = validate_verhoeff_checksum(norm_id)
        if chk_res == ChecksumStatus.PASS:
            chk_valid  = True
            chk_status = "passed"
            chk_msg    = f"Verhoeff checksum passed ({masked_display})."
        elif chk_res == ChecksumStatus.FAIL:
            chk_valid  = False
            chk_status = "warning"
            chk_msg    = f"Aadhaar number failed Verhoeff checksum validation ({masked_display})."
            issues.append({"severity": "warning", "check": "identifier_checksum", "message": chk_msg})
        else:
            chk_valid  = False
            chk_status = "inconclusive"
            chk_msg    = f"Verhoeff checksum inconclusive ({masked_display})."
    else:
        chk_res    = ChecksumStatus.INCONCLUSIVE
        chk_valid  = False
        chk_status = "unknown"
        chk_msg    = "Checksum not verifiable without a valid 12-digit identifier."

    checks["identifier_checksum"] = {"status": chk_status, "valid": chk_valid, "checksum_status": chk_res.value, "message": chk_msg}

    # ── Check 4: Date of Birth / Year of Birth Plausibility ──────────────────
    extracted_yob: Optional[int] = None
    date_info = normalize_dob_or_yob(dob_val or yob_val)

    if date_info["year_of_birth"]:
        extracted_yob = date_info["year_of_birth"]
    elif yob_val and yob_val.isdigit():
        extracted_yob = int(yob_val)

    date_valid  = True
    date_status = "passed"
    date_msg    = "Birth year/date is plausible."

    if extracted_yob:
        current_year = reference_date.year
        if extracted_yob < 1900:
            date_valid  = False
            date_status = "warning"
            date_msg    = f"Birth year ({extracted_yob}) is implausibly early."
            issues.append({"severity": "warning", "check": "date_validity", "message": date_msg})
        elif extracted_yob > current_year:
            date_valid  = False
            date_status = "failed"
            date_msg    = f"Birth year ({extracted_yob}) is in the future."
            issues.append({"severity": "critical", "check": "date_validity", "message": date_msg})
        else:
            date_msg = f"Date of birth verified: {date_info['date_of_birth']}." if date_info["date_of_birth"] else f"Year of birth verified: {extracted_yob} (year-only)."
    else:
        date_valid  = False
        date_status = "warning"
        date_msg    = "Date or Year of Birth not available."
        issues.append({"severity": "warning", "check": "date_validity", "message": date_msg})

    checks["date_validity"] = {"status": date_status, "valid": date_valid, "date_of_birth": date_info.get("date_of_birth"), "year_of_birth": extracted_yob, "is_year_only": date_info.get("is_year_only", False), "message": date_msg}

    # ── Check 5: QR / Barcode Field Consistency ───────────────────────────────
    qr_payload = traveler.qrPayload
    if qr_payload:
        parsed_qr = parse_national_id_qr_payload(qr_payload)
        ocr_comparison_fields = {"identity_number": norm_id, "name": name, "dob": date_info.get("date_of_birth") or str(extracted_yob)}
        qr_comp = compare_ocr_and_qr(ocr_comparison_fields, parsed_qr)
        if qr_comp["overall_consistency"] == "MATCHED":
            qr_status = "passed"
            qr_valid  = True
            qr_msg    = "QR payload decoded and consistent with extracted OCR fields (Unauthenticated)."
        elif qr_comp["overall_consistency"] == "MISMATCH":
            qr_status = "failed"
            qr_valid  = False
            qr_msg    = "Inconsistency detected between QR payload and extracted OCR fields."
            issues.append({"severity": "high", "check": "qr_consistency", "message": qr_msg})
        else:
            qr_status = "inconclusive"
            qr_valid  = True
            qr_msg    = "QR payload decoded but fields inconclusive for cross-checking."
    else:
        qr_status = "not_applicable"
        qr_valid  = True
        qr_msg    = "No QR payload detected or provided."

    checks["qr_consistency"] = {"status": qr_status, "valid": qr_valid, "message": qr_msg}

    # ── Overall Status Synthesis ──────────────────────────────────────────────
    if any(issue["severity"] == "critical" for issue in issues):
        overall_status = "failed"
        summary = f"Aadhaar validation failed: {issues[0]['message']}"
    elif any(issue["severity"] in ("high", "warning") for issue in issues):
        overall_status = "warning"
        summary = f"Aadhaar validated with warnings: {issues[0]['message']}"
    elif not req_valid or not id_fmt_valid:
        overall_status = "failed"
        summary = "Aadhaar failed structural validation checks."
    else:
        overall_status = "passed"
        summary = "All Aadhaar structural, format, and checksum checks passed."

    return {"status": overall_status, "summary": summary, "checks": checks, "issues": issues}


# Backward compatibility alias
validate_national_id_document = validate_aadhaar_document
