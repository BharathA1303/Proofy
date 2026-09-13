"""
backend/app/services/documents/driving_license/dl_validator.py

Module 2: Driving License Document Structural and Eligibility Validation Service.

Validates structural integrity, required fields, identifier format,
date chronology, class-specific age eligibility, and expiration status.

CRITICAL ARCHITECTURAL CONTRACTS:
  - This is STRUCTURAL VALIDATION, not an authenticity/forensic determination.
  - Answers: "Does the extracted DL information satisfy the configured structural,
    chronology, and eligibility rules?"
  - NEVER outputs "FORGED_DOCUMENT". Authenticity/forensic determination belongs
    to M3/M4/M5 and later evidence fusion.
  - Required fields and class-specific age rules are 100% profile-driven.
  - Preserves ambiguity and candidate provenance from Phase 2 and Phase 5.
"""
from __future__ import annotations

import datetime
import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from app.schemas.ocr import TravelerFields
from app.services.documents.driving_license.dl_field_normalizer import (
    STATE_CODE_REGISTRY,
    StateCodeEntry,
    StateCodeStatus,
    _INDIAN_STATE_CODES,
    extract_state_from_license_number,
    normalize_dl_date,
    normalize_license_number,
    normalize_vehicle_classes,
    normalize_vehicle_classes_detailed,
)
from app.services.documents.profiles.document_profile import DocumentProfile
from app.services.documents.profiles.driving_license_profile import DRIVING_LICENSE_PROFILE

logger = logging.getLogger(__name__)


# ── Canonical M2 Structural Statuses ──────────────────────────────────────────

class StructuralValidationStatus(str, Enum):
    """Overall structural validation conclusion from Module 2."""
    STRUCTURALLY_VALID = "STRUCTURALLY_VALID"
    STRUCTURALLY_VALID_WITH_WARNINGS = "STRUCTURALLY_VALID_WITH_WARNINGS"
    INCONCLUSIVE = "INCONCLUSIVE"
    STRUCTURALLY_INVALID = "STRUCTURALLY_INVALID"


class ValidationCheckStatus(str, Enum):
    """Detailed status for individual structural checks."""
    VALID = "VALID"
    MISSING = "MISSING"
    INVALID = "INVALID"
    AMBIGUOUS = "AMBIGUOUS"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    EXPIRED = "EXPIRED"
    FORMAT_WARNING = "FORMAT_WARNING"
    LEGACY_VALID = "LEGACY_VALID"
    STATE_CODE_VALID = "STATE_CODE_VALID"
    STATE_CODE_LEGACY = "STATE_CODE_LEGACY"
    STATE_CODE_UNKNOWN = "STATE_CODE_UNKNOWN"
    UNKNOWN_COV = "UNKNOWN_COV"


# ── Internal Field Information Helper ─────────────────────────────────────────

class _ExtractedFieldInfo:
    """Internal normalized representation of a field candidate for validation."""
    def __init__(
        self,
        value: Optional[str] = None,
        status: str = "VALID",
        raw: Optional[str] = None,
        confidence: Optional[float] = None,
        semantic_confidence: Optional[float] = None,
        ocr_confidence: Optional[float] = None,
        source: Optional[str] = None,
        candidates: Optional[List[Any]] = None,
        evidence: Optional[List[str]] = None,
    ) -> None:
        self.value = value
        self.status = status
        self.raw = raw
        self.confidence = confidence
        self.semantic_confidence = semantic_confidence
        self.ocr_confidence = ocr_confidence
        self.source = source
        self.candidates = candidates or []
        self.evidence = evidence or []


def _resolve_field_info(
    field_name: str,
    traveler: Optional[TravelerFields] = None,
    semantic_result: Optional[Any] = None,
    parsed_dl: Optional[Any] = None,
    extracted_fields: Optional[Dict[str, Any]] = None,
) -> _ExtractedFieldInfo:
    """
    Resolve extracted field value, status, confidence, and provenance
    across semantic extraction (Phase 5), parsed DL (Phase 2), dicts, or TravelerFields.
    """
    # 1. Check SemanticExtractionResult (Phase 5)
    if semantic_result is not None and hasattr(semantic_result, "fields"):
        # Check direct or mapped key
        key = field_name
        if key not in semantic_result.fields:
            alias_map = {
                "docNumber": "license_number",
                "issuedDate": "issue_date",
                "expiry": "valid_to",
                "vehicleClass": "vehicle_classes",
                "bloodGroup": "blood_group",
                "authority": "issuing_authority",
            }
            key = alias_map.get(key, key)

        if key in semantic_result.fields:
            s_field = semantic_result.fields[key]
            st_val = getattr(s_field.status, "value", str(s_field.status))
            norm_st = "AMBIGUOUS" if st_val == "AMBIGUOUS" else (
                "MISSING" if st_val == "MISSING" else (
                    "LOW_CONFIDENCE" if st_val == "LOW_CONFIDENCE" else "VALID"
                )
            )
            return _ExtractedFieldInfo(
                value=s_field.normalized_value or s_field.value,
                status=norm_st,
                raw=s_field.raw,
                confidence=s_field.confidence,
                semantic_confidence=s_field.semantic_confidence,
                ocr_confidence=s_field.ocr_confidence,
                source=s_field.source,
                candidates=s_field.candidates,
                evidence=s_field.evidence,
            )

    # 2. Check ParsedDrivingLicenseData (Phase 2)
    if parsed_dl is not None:
        dl_f = getattr(parsed_dl, field_name, None)
        if dl_f is not None and hasattr(dl_f, "status"):
            st_val = getattr(dl_f.status, "value", str(dl_f.status))
            norm_st = "AMBIGUOUS" if st_val == "AMBIGUOUS" else (
                "MISSING" if st_val == "MISSING" else (
                    "LOW_CONFIDENCE" if st_val == "LOW_CONFIDENCE" else "VALID"
                )
            )
            return _ExtractedFieldInfo(
                value=dl_f.value,
                status=norm_st,
                raw=dl_f.raw,
                confidence=dl_f.confidence,
                source=dl_f.source,
                candidates=dl_f.candidates,
            )

    # 3. Check extracted_fields dict
    if extracted_fields and field_name in extracted_fields:
        val_entry = extracted_fields[field_name]
        if isinstance(val_entry, dict):
            return _ExtractedFieldInfo(
                value=val_entry.get("value"),
                status=val_entry.get("status", "VALID"),
                raw=val_entry.get("raw"),
                confidence=val_entry.get("confidence"),
                source=val_entry.get("source"),
                candidates=val_entry.get("candidates", []),
                evidence=val_entry.get("evidence", []),
            )
        elif isinstance(val_entry, str):
            clean_s = val_entry.strip()
            if clean_s.upper() == "AMBIGUOUS":
                return _ExtractedFieldInfo(value=None, status="AMBIGUOUS")
            if not clean_s:
                return _ExtractedFieldInfo(value=None, status="MISSING")
            return _ExtractedFieldInfo(value=clean_s, status="VALID")

    # 4. Check TravelerFields
    if traveler:
        tf_map = {
            "name": traveler.name,
            "docNumber": traveler.docNumber or traveler.licenseNumber,
            "license_number": traveler.docNumber or traveler.licenseNumber,
            "licenseNumber": traveler.licenseNumber or traveler.docNumber,
            "dob": traveler.dob,
            "issuedDate": traveler.issuedDate or traveler.validFrom,
            "valid_from": traveler.validFrom or traveler.issuedDate,
            "expiry": traveler.expiry or traveler.validTo,
            "valid_to": traveler.validTo or traveler.expiry,
            "transport_validity": getattr(traveler, "transport_validity", None) or getattr(traveler, "transportValidity", None),
            "vehicle_classes": traveler.vehicleClass,
            "vehicleClass": traveler.vehicleClass,
            "state": traveler.state,
            "blood_group": traveler.bloodGroup,
            "bloodGroup": traveler.bloodGroup,
            "authority": traveler.authority,
        }
        val = tf_map.get(field_name)
        if val is not None:
            clean_s = str(val).strip()
            if clean_s.upper() == "AMBIGUOUS":
                return _ExtractedFieldInfo(value=None, status="AMBIGUOUS")
            if not clean_s:
                return _ExtractedFieldInfo(value=None, status="MISSING")
            return _ExtractedFieldInfo(value=clean_s, status="VALID")

    return _ExtractedFieldInfo(value=None, status="MISSING")


# ── Main Driving License Document Validation Function ─────────────────────────

def validate_driving_license_document(
    traveler: Optional[TravelerFields] = None,
    reference_date: Optional[datetime.date] = None,
    *,
    semantic_result: Optional[Any] = None,
    parsed_dl: Optional[Any] = None,
    profile: Optional[DocumentProfile] = None,
    extracted_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute structural, chronology, and class-specific eligibility validation on Driving License data.

    Returns a structured dictionary compatible with DocumentValidationSummary:
      - status: 'passed' | 'warning' | 'failed' | 'insufficient_data'
      - structural_status: 'STRUCTURALLY_VALID' | 'STRUCTURALLY_VALID_WITH_WARNINGS' | 'INCONCLUSIVE' | 'STRUCTURALLY_INVALID'
      - summary: explainable text
      - checks: dictionary of individual check evidence items
      - issues: list of ValidationIssue dictionaries
      - document_type: "driving_license"
      - jurisdiction: "IN"
      - profile_version: profile version string
    """
    if reference_date is None:
        reference_date = datetime.date.today()

    if profile is None:
        profile = DRIVING_LICENSE_PROFILE

    # Extract declarative profile configurations
    val_cfg = getattr(profile, "validation_config", {})
    prof_version = val_cfg.get("profile_version", profile.version)
    jurisdiction = val_cfg.get("jurisdiction", getattr(profile, "jurisdiction", "IN"))

    # Return insufficient_data when no inputs provided at all
    if not traveler and not semantic_result and not parsed_dl and not extracted_fields:
        return {
            "status": "insufficient_data",
            "structural_status": StructuralValidationStatus.INCONCLUSIVE.value,
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
            "document_type": profile.document_type,
            "jurisdiction": jurisdiction,
            "profile_version": prof_version,
        }

    issues: List[Dict[str, Any]] = []
    checks: Dict[str, Any] = {}

    # Extract all relevant fields via unified resolver
    name_info = _resolve_field_info("name", traveler, semantic_result, parsed_dl, extracted_fields)
    doc_info = _resolve_field_info("docNumber", traveler, semantic_result, parsed_dl, extracted_fields)
    dob_info = _resolve_field_info("dob", traveler, semantic_result, parsed_dl, extracted_fields)
    issue_info = _resolve_field_info("issuedDate", traveler, semantic_result, parsed_dl, extracted_fields)
    expiry_info = _resolve_field_info("expiry", traveler, semantic_result, parsed_dl, extracted_fields)
    tr_info = _resolve_field_info("transport_validity", traveler, semantic_result, parsed_dl, extracted_fields)
    cov_info = _resolve_field_info("vehicle_classes", traveler, semantic_result, parsed_dl, extracted_fields)
    state_info = _resolve_field_info("state", traveler, semantic_result, parsed_dl, extracted_fields)

    # ── Check 1: Required Field Presence (Profile-Driven) ─────────────────────
    req_fields = val_cfg.get("required_fields", profile.required_fields or ["name", "docNumber", "dob"])
    missing_fields: List[str] = []
    ambiguous_fields: List[str] = []
    field_evidence: Dict[str, Any] = {}

    for rf in req_fields:
        f_info = _resolve_field_info(rf, traveler, semantic_result, parsed_dl, extracted_fields)
        if f_info.status == "AMBIGUOUS":
            ambiguous_fields.append(rf)
            field_evidence[rf] = {"status": "AMBIGUOUS", "value": None}
        elif f_info.status == "MISSING" or not f_info.value:
            missing_fields.append(rf)
            field_evidence[rf] = {"status": "MISSING", "value": None}
        elif f_info.status == "LOW_CONFIDENCE":
            field_evidence[rf] = {"status": "LOW_CONFIDENCE", "value": f_info.value, "confidence": f_info.confidence}
        else:
            field_evidence[rf] = {"status": "VALID", "value": f_info.value}

    if missing_fields:
        req_valid = False
        req_status = "failed"
        req_msg = f"Missing required fields: {', '.join(missing_fields)}."
        issues.append({
            "severity": "critical",
            "check": "required_fields",
            "message": req_msg,
            "check_id": "REQUIRED_FIELD_MISSING",
        })
    elif ambiguous_fields:
        req_valid = False
        req_status = "warning"
        req_msg = f"Required field(s) ambiguous: {', '.join(ambiguous_fields)}."
        issues.append({
            "severity": "warning",
            "check": "required_fields",
            "message": req_msg,
            "check_id": "REQUIRED_FIELD_AMBIGUOUS",
        })
    else:
        req_valid = True
        req_status = "passed"
        req_msg = "All primary required fields are present."

    checks["required_fields"] = {
        "status": req_status,
        "valid": req_valid,
        "message": req_msg,
        "fields": field_evidence,
        "check_id": "REQUIRED_FIELD_PRESENCE",
        "profile_version": prof_version,
    }

    # ── Check 2: License Number Validation (Current, Legacy, Plausible) ────────
    raw_doc_num = doc_info.raw or doc_info.value or ""
    clean_doc_num = raw_doc_num.strip()

    id_rules = val_cfg.get("identifier_rules", {})
    canonical_pat = id_rules.get("canonical_pattern", r"^[A-Z]{2}[0-9]{2}(?:19|20)[0-9]{2}[0-9]{7}$")
    legacy_pats = id_rules.get("legacy_patterns", [
        r"^[A-Z]{2}[0-9]{2}[0-9]{7,11}$",
        r"^[A-Z]{2}[-\s]?[0-9]{2}[-\s]?(?:19|20)?[0-9]{2,4}[-\s]?[0-9]{4,8}$",
        r"^DL[-\s]?[A-Z0-9]{10,16}$",
    ])
    plausible_pat = id_rules.get("plausible_pattern", r"^[A-Z]{2}[A-Z0-9\-\s/]{7,22}$")

    if doc_info.status == "AMBIGUOUS":
        num_valid = False
        num_status = "warning"
        num_msg = "License number is ambiguous (multiple competing values detected)."
        issues.append({
            "severity": "warning",
            "check": "license_number_format",
            "message": num_msg,
            "check_id": "IDENTIFIER_AMBIGUOUS",
        })
    elif clean_doc_num:
        norm_num = normalize_license_number(clean_doc_num)
        if norm_num and re.match(canonical_pat, norm_num):
            num_valid = True
            num_status = "passed"
            identifier_status = "VALID"
            num_msg = f"License number '{norm_num}' conforms to canonical MoRTH standard."
        elif norm_num and (any(re.match(p, norm_num) for p in legacy_pats) or re.match(r"^[A-Z]{2}\d{2}\d{7,11}$", norm_num)):
            num_valid = True
            num_status = "passed"
            identifier_status = "LEGACY_VALID"
            num_msg = f"License number '{norm_num}' matches recognized legacy state DL format."
        elif (norm_num and re.match(plausible_pat, norm_num)) or re.match(plausible_pat, clean_doc_num.replace(" ", "")):
            num_valid = False
            num_status = "warning"
            identifier_status = "FORMAT_WARNING"
            num_msg = f"The extracted identifier '{clean_doc_num}' does not confidently match the supported reference profile."
            issues.append({
                "severity": "warning",
                "check": "license_number_format",
                "message": num_msg,
                "check_id": "IDENTIFIER_FORMAT_WARNING",
            })
        else:
            num_valid = False
            num_status = "warning"
            identifier_status = "INVALID"
            num_msg = f"The extracted identifier '{clean_doc_num}' does not confidently match the supported reference profile."
            issues.append({
                "severity": "warning",
                "check": "license_number_format",
                "message": num_msg,
                "check_id": "IDENTIFIER_INVALID",
            })
    else:
        norm_num = None
        num_valid = False
        num_status = "failed"
        identifier_status = "MISSING"
        num_msg = "License number is absent or unparseable."
        issues.append({
            "severity": "critical",
            "check": "license_number_format",
            "message": num_msg,
            "check_id": "IDENTIFIER_MISSING",
        })

    checks["license_number_format"] = {
        "status": num_status,
        "valid": num_valid,
        "identifier_status": identifier_status if clean_doc_num else "MISSING",
        "message": num_msg,
        "normalized_identifier": norm_num,
        "check_id": "LICENSE_NUMBER_FORMAT",
        "profile_version": prof_version,
    }

    # ── Check 3: State / Region Code Validation ──────────────────────────────
    state_code = (norm_num or clean_doc_num)[:2].upper() if len(norm_num or clean_doc_num) >= 2 else ""
    state_entry = STATE_CODE_REGISTRY.get(state_code)
    state_provenance = state_info.source or ("DERIVED_FROM_LICENSE_NUMBER" if state_code else None)

    if state_entry:
        if state_entry.code_status == StateCodeStatus.CURRENT:
            st_check_status = "passed"
            st_check_valid = True
            st_code_status = "STATE_CODE_VALID"
            st_msg = f"State code '{state_code}' corresponds to {state_entry.canonical_state}."
        else:
            st_check_status = "warning"
            st_check_valid = True
            st_code_status = "STATE_CODE_LEGACY"
            st_msg = f"State code '{state_code}' is a recognized legacy code ({state_entry.canonical_state})."
            issues.append({
                "severity": "info",
                "check": "state_validation",
                "message": st_msg,
                "check_id": "STATE_CODE_LEGACY",
            })
    elif state_code and re.match(r"^[A-Z]{2}$", state_code):
        st_check_status = "warning"
        st_check_valid = False
        st_code_status = "STATE_CODE_UNKNOWN"
        st_msg = f"State code '{state_code}' is unrecognized or unassigned."
        issues.append({
            "severity": "warning",
            "check": "state_validation",
            "message": st_msg,
            "check_id": "STATE_CODE_UNKNOWN",
        })
    else:
        st_check_status = "unknown"
        st_check_valid = False
        st_code_status = "UNKNOWN"
        st_msg = "State code could not be extracted from document or identifier."

    checks["state_validation"] = {
        "status": st_check_status,
        "valid": st_check_valid,
        "state_code": state_code or None,
        "state_name": state_entry.canonical_state if state_entry else None,
        "state_code_status": st_code_status,
        "provenance": state_provenance,
        "message": st_msg,
        "check_id": "STATE_VALIDATION",
        "profile_version": prof_version,
    }

    # ── Check 4: Date Role Integrity & Chronology ─────────────────────────────
    parsed_dob = _parse_date(dob_info.value)
    parsed_issue = _parse_date(issue_info.value)
    parsed_expiry = _parse_date(expiry_info.value)

    chrono_valid = True
    chrono_status = "passed"
    chrono_msg = "Dates are logically consistent."

    # Check for ambiguity in dates
    dates_ambiguous = (
        dob_info.status == "AMBIGUOUS"
        or issue_info.status == "AMBIGUOUS"
        or expiry_info.status == "AMBIGUOUS"
    )

    if dates_ambiguous:
        chrono_status = "inconclusive"
        chrono_valid = False
        chrono_msg = "One or more dates are ambiguous; cannot evaluate chronology."
    elif parsed_dob and parsed_dob > reference_date:
        chrono_valid = False
        chrono_status = "failed"
        chrono_msg = f"Date of birth ({parsed_dob}) is in the future."
        issues.append({
            "severity": "critical",
            "check": "date_chronology",
            "message": chrono_msg,
            "check_id": "FUTURE_DOB",
        })
    elif parsed_issue and parsed_expiry and parsed_issue > parsed_expiry:
        chrono_valid = False
        chrono_status = "failed"
        chrono_msg = f"Inverted validity: issue date ({parsed_issue}) is after expiry date ({parsed_expiry})."
        issues.append({
            "severity": "critical",
            "check": "date_chronology",
            "message": chrono_msg,
            "check_id": "INVERTED_VALIDITY",
        })
    elif parsed_dob and parsed_issue and parsed_dob >= parsed_issue:
        chrono_valid = False
        chrono_status = "failed"
        chrono_msg = f"Inverted dates: date of birth ({parsed_dob}) is on or after issue date ({parsed_issue})."
        issues.append({
            "severity": "critical",
            "check": "date_chronology",
            "message": chrono_msg,
            "check_id": "DOB_AFTER_ISSUE",
        })
    elif parsed_dob and parsed_expiry and parsed_dob >= parsed_expiry:
        chrono_valid = False
        chrono_status = "failed"
        chrono_msg = f"Inverted dates: date of birth ({parsed_dob}) is on or after expiry date ({parsed_expiry})."
        issues.append({
            "severity": "critical",
            "check": "date_chronology",
            "message": chrono_msg,
            "check_id": "DOB_AFTER_EXPIRY",
        })
    elif parsed_issue and parsed_expiry:
        chrono_msg = f"Valid from {parsed_issue} to {parsed_expiry}."
    elif not parsed_issue and not parsed_expiry:
        chrono_status = "unknown"
        chrono_msg = "Validity dates not available for chronology check."

    checks["date_chronology"] = {
        "status": chrono_status,
        "valid": chrono_valid,
        "message": chrono_msg,
        "check_id": "DATE_CHRONOLOGY",
        "profile_version": prof_version,
    }

    # ── Check 5: Expiration Status ───────────────────────────────────────────
    if expiry_info.status == "AMBIGUOUS":
        is_expired = None
        exp_valid = False
        exp_status = "ambiguous"
        exp_classification = "AMBIGUOUS"
        exp_msg = "Expiry date is ambiguous (multiple competing dates detected)."
        issues.append({
            "severity": "warning",
            "check": "expiry_date",
            "message": exp_msg,
            "check_id": "EXPIRY_AMBIGUOUS",
        })
    elif parsed_expiry:
        is_expired = parsed_expiry < reference_date
        exp_valid = not is_expired
        exp_status = "failed" if is_expired else "passed"
        exp_classification = "EXPIRED" if is_expired else "VALID"
        exp_msg = f"Driving license expired on {parsed_expiry}." if is_expired else f"License is active (expires {parsed_expiry})."
        if is_expired:
            issues.append({
                "severity": "critical",
                "check": "expiry_date",
                "message": exp_msg,
                "check_id": "LICENSE_EXPIRED",
            })
    else:
        is_expired = None
        exp_valid = True
        exp_status = "unknown"
        exp_classification = "MISSING"
        exp_msg = "Expiry date not available."

    checks["expiry_date"] = {
        "status": exp_status,
        "valid": exp_valid,
        "expired": is_expired,
        "classification": exp_classification,
        "expiry_date": parsed_expiry.isoformat() if parsed_expiry else None,
        "message": exp_msg,
        "check_id": "EXPIRY_EVALUATION",
        "profile_version": prof_version,
    }

    # ── Check 6: Class-Specific Age Eligibility (Profile-Driven) ─────────────
    age_rules = val_cfg.get("age_rules", {})
    class_rules: Dict[str, int] = age_rules.get("class_rules", {
        "MCWOG": 16, "M/CYCL.WOG": 16, "MC WITHOUT GEAR": 16,
        "LMV": 18, "LMV-NT": 18, "MCWG": 18, "M/CYCL.WG": 18,
        "TRANS": 20, "HGMV": 20, "HTV": 20, "LMV-TR": 20,
    })
    default_min_age: int = age_rules.get("default_min_age", 18)
    max_plausible_age: int = age_rules.get("max_plausible_age", 110)

    age_valid = True
    age_status = "passed"
    age_msg = "Holder age is valid."
    age_years: Optional[float] = None

    if parsed_dob:
        calc_reference = parsed_issue or reference_date
        age_years = (calc_reference - parsed_dob).days / 365.25

        if age_years > max_plausible_age:
            age_valid = False
            age_status = "warning"
            age_msg = f"Date of birth indicates implausible age ({age_years:.1f} years)."
            issues.append({
                "severity": "warning",
                "check": "age_eligibility",
                "message": age_msg,
                "check_id": "IMPLAUSIBLE_AGE",
            })
        else:
            raw_cov = cov_info.value or ""
            clean_cov = raw_cov.strip()

            if clean_cov:
                cov_detail = normalize_vehicle_classes_detailed(clean_cov)
                valid_covs = cov_detail.recognized
                unknown_covs = cov_detail.unrecognized
                if not valid_covs and not unknown_covs:
                    unknown_covs = [clean_cov]

                if unknown_covs and not valid_covs or clean_cov.upper() in ["UNKNOWN", "XYZ", "UNKNOWN_COV"]:
                    age_valid = False
                    age_status = "inconclusive"
                    age_msg = f"Vehicle class '{clean_cov}' is unknown; cannot determine applicable age eligibility rule."
                else:
                    # Evaluate minimum age for all endorsed vehicle classes
                    failed_classes = []
                    for vc in valid_covs:
                        req_age = class_rules.get(vc.upper(), default_min_age)
                        if age_years < req_age:
                            failed_classes.append((vc, req_age))

                    if failed_classes:
                        age_valid = False
                        age_status = "failed"
                        primary_fail = failed_classes[0]
                        age_msg = f"Underage driver for class '{primary_fail[0]}': age at reference/issue date is {age_years:.1f} years (minimum {primary_fail[1]} required)."
                        issues.append({
                            "severity": "critical",
                            "check": "age_eligibility",
                            "message": age_msg,
                            "check_id": "AGE_ELIGIBILITY_FAILED",
                        })
                    else:
                        age_valid = True
                        age_status = "passed"
                        age_msg = f"Holder age verified ({int(age_years)} years) for class(es) {', '.join(valid_covs)}."
            else:
                # No COV specified
                if age_years >= default_min_age:
                    age_valid = True
                    age_status = "passed"
                    age_msg = f"Holder age verified ({int(age_years)} years)."
                elif age_years < 16.0:
                    age_valid = False
                    age_status = "failed"
                    age_msg = f"Underage driver: age at reference/issue date is {age_years:.1f} years (minimum {default_min_age} required)."
                    issues.append({
                        "severity": "critical",
                        "check": "age_eligibility",
                        "message": age_msg,
                        "check_id": "AGE_ELIGIBILITY_FAILED",
                    })
                else:
                    # Age between 16 and 18 without vehicle class
                    age_valid = False
                    age_status = "inconclusive"
                    age_msg = f"Age ({age_years:.1f} years) requires vehicle class to determine eligibility (16 for MCWOG, 18 for LMV)."
    else:
        age_status = "unknown"
        age_valid = False
        age_msg = "Date of birth not available for age verification."

    checks["age_eligibility"] = {
        "status": age_status,
        "valid": age_valid,
        "age_years": round(age_years, 1) if age_years is not None else None,
        "message": age_msg,
        "check_id": "AGE_ELIGIBILITY",
        "profile_version": prof_version,
    }

    # ── Check 7: Vehicle Class Validation (Taxonomy & Conservatism) ───────────
    raw_cov = cov_info.value or ""
    cov_rules = val_cfg.get("cov_rules", {})
    transport_classes: Set[str] = set(cov_rules.get("transport_classes", [
        "TRANS", "HGMV", "HPMV", "HTV", "HPV", "HGV", "MGV", "MMV", "MPV", "LMV-TR", "3W-TR", "PSV"
    ]))

    if raw_cov.strip():
        cov_detail = normalize_vehicle_classes_detailed(raw_cov)
        valid_covs = cov_detail.recognized
        unknown_covs = cov_detail.unrecognized
        if not valid_covs and not unknown_covs:
            unknown_covs = [raw_cov.strip()]
        if unknown_covs:
            cov_valid = True  # Conservative: do not reject document solely due to unrecognized COV
            cov_status = "warning"
            cov_msg = f"Unrecognized vehicle class(es): {', '.join(unknown_covs)}."
            issues.append({
                "severity": "warning",
                "check": "vehicle_class_validation",
                "message": cov_msg,
                "check_id": "UNKNOWN_COV",
            })
        else:
            cov_valid = True
            cov_status = "passed"
            cov_msg = f"Vehicle classes recognized: {', '.join(valid_covs)}."
    else:
        valid_covs, unknown_covs = [], []
        cov_valid = True
        cov_status = "passed"
        cov_msg = "Vehicle class not specified (not mandatory for generic validity)."

    checks["vehicle_class_validation"] = {
        "status": cov_status,
        "valid": cov_valid,
        "recognized_classes": valid_covs,
        "unrecognized_classes": unknown_covs,
        "message": cov_msg,
        "check_id": "VEHICLE_CLASS_VALIDATION",
        "profile_version": prof_version,
    }

    # ── Check 8: Transport / Non-Transport Validity & Consistency ─────────────
    has_transport_cov = any(c.upper() in transport_classes for c in valid_covs)
    parsed_tr = _parse_date(tr_info.value)

    if parsed_tr:
        is_tr_expired = parsed_tr < reference_date
        tr_valid = not is_tr_expired
        tr_status = "failed" if is_tr_expired else "passed"
        tr_msg = f"Transport validity active until {parsed_tr}." if not is_tr_expired else f"Transport validity expired on {parsed_tr}."
        if is_tr_expired:
            issues.append({
                "severity": "critical",
                "check": "transport_validity",
                "message": tr_msg,
                "check_id": "TRANSPORT_VALIDITY_EXPIRED",
            })
    elif tr_info.value:
        tr_valid = False
        tr_status = "warning"
        tr_msg = f"Transport validity date unparseable: '{tr_info.value}'."
        issues.append({
            "severity": "warning",
            "check": "transport_validity",
            "message": tr_msg,
            "check_id": "TRANSPORT_VALIDITY_INVALID",
        })
    else:
        # TR validity is absent
        if has_transport_cov:
            tr_valid = False
            tr_status = "warning"
            tr_msg = "Transport vehicle class endorsed but transport validity date is absent."
            issues.append({
                "severity": "warning",
                "check": "cov_validity_consistency",
                "message": tr_msg,
                "check_id": "TRANSPORT_VALIDITY_MISSING",
            })
        else:
            tr_valid = True
            tr_status = "passed"
            tr_msg = "Transport validity not applicable for non-transport vehicle classes."

    checks["transport_validity"] = {
        "status": tr_status,
        "valid": tr_valid,
        "transport_expiry": parsed_tr.isoformat() if parsed_tr else None,
        "transport_endorsed": has_transport_cov,
        "message": tr_msg,
        "check_id": "TRANSPORT_VALIDITY",
        "profile_version": prof_version,
    }

    # ── Overall M2 Status Synthesis ──────────────────────────────────────────
    # CRITICAL: Structural validation NEVER outputs FORGED_DOCUMENT!
    has_critical = any(issue["severity"] == "critical" for issue in issues)
    has_warning = any(issue["severity"] in ["warning", "info"] for issue in issues)
    is_inconclusive = any(
        chk.get("status") in ["inconclusive", "insufficient_data"]
        for chk in checks.values()
    )

    if has_critical or not req_valid or not num_valid:
        structural_status = StructuralValidationStatus.STRUCTURALLY_INVALID
        overall_status = "failed"
        critical_issues = [i for i in issues if i.get("severity") == "critical"]
        summary = f"Driving License validation failed: {critical_issues[0]['message'] if critical_issues else 'Primary structural checks failed.'}"
    elif has_warning:
        structural_status = StructuralValidationStatus.STRUCTURALLY_VALID_WITH_WARNINGS
        overall_status = "warning"
        warning_issues = [i for i in issues if i.get("severity") in ["warning", "info"]]
        summary = f"Driving License validated with warnings: {warning_issues[0]['message'] if warning_issues else 'Structural warnings present.'}"
    elif is_inconclusive:
        structural_status = StructuralValidationStatus.INCONCLUSIVE
        overall_status = "insufficient_data"
        summary = "Driving License structural validation is inconclusive."
    else:
        structural_status = StructuralValidationStatus.STRUCTURALLY_VALID
        overall_status = "passed"
        summary = "All Driving License structural and chronology checks passed."

    return {
        "status": overall_status,
        "structural_status": structural_status.value,
        "summary": summary,
        "checks": checks,
        "issues": issues,
        "document_type": profile.document_type,
        "jurisdiction": jurisdiction,
        "profile_version": prof_version,
    }


def _parse_date(date_str: Optional[str]) -> Optional[datetime.date]:
    """Safely parse a date string into datetime.date without guessing."""
    if not date_str:
        return None
    iso_date = normalize_dl_date(str(date_str))
    if not iso_date:
        return None
    try:
        parts = [int(p) for p in iso_date.split("-")]
        return datetime.date(parts[0], parts[1], parts[2])
    except (ValueError, IndexError):
        return None
