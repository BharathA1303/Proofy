"""
backend/app/services/validation/passport_validation_service.py

Module 2: Passport Document Validation Service.

Orchestrates:
1. MRZ TD3 structural validation
2. ICAO 7-3-1 check digits (Doc Number, DOB, Expiry, Composite)
3. Date format, calendar correctness, and expiry checking
4. The Passport Number Binding Trap (VIZ <-> MRZ cross-check)
5. Comprehensive VIZ <-> MRZ field consistency checks

Produces a structured, explainable DocumentValidationSummary.
Adheres strictly to event-level logging (NO PII logged).
"""
from __future__ import annotations

import datetime
import logging
from typing import Optional

from app.schemas.ocr import MRZData, TravelerFields
from app.schemas.validation import (
    CheckDigitEvidence,
    CheckItem,
    DocumentValidationSummary,
    ExpiryCheckEvidence,
    FieldConsistencyItem,
    PassportBindingEvidence,
    ValidationChecks,
    ValidationIssue,
    VizMrzConsistencyReport,
)
from app.services.validation.date_validator import parse_mrz_date, validate_expiry
from app.services.validation.icao_checkdigit import validate_check_digit
from app.services.validation.mrz_validator import normalize_mrz_line, validate_td3_structure
from app.services.validation.viz_mrz_checker import (
    compare_date_field,
    compare_gender_field,
    compare_name_field,
    compare_nationality_field,
    compare_text_field,
    validate_passport_binding,
)

logger = logging.getLogger(__name__)


def validate_passport_document(
    mrz_data: Optional[MRZData],
    traveler: Optional[TravelerFields],
    reference_date: Optional[datetime.date] = None,
) -> DocumentValidationSummary:
    """
    Execute all Module 2 document validation checks on extracted passport data.

    Args:
        mrz_data: MRZ lines extracted during Module 1 OCR.
        traveler: Structured traveler fields extracted from VIZ and MRZ.
        reference_date: Evaluation date for expiration (defaults to today).

    Returns:
        DocumentValidationSummary with complete check evidence and overall status.
    """
    if reference_date is None:
        reference_date = datetime.date.today()

    issues: list[ValidationIssue] = []

    raw_l1 = mrz_data.line1 if mrz_data else None
    raw_l2 = mrz_data.line2 if mrz_data else None

    # ─────────────────────────────────────────────────────────────
    # Check 1: MRZ Structure Validation
    # ─────────────────────────────────────────────────────────────
    struct_res = validate_td3_structure(raw_l1, raw_l2)

    mrz_check_item = CheckItem(
        status=struct_res.status,
        valid=struct_res.valid,
        message=struct_res.message,
    )

    for iss in struct_res.issues:
        issues.append(
            ValidationIssue(
                severity="critical" if "missing" in iss.lower() or "character" in iss.lower() else "warning",
                check="mrz_structure",
                message=iss,
            )
        )

    # If no MRZ lines at all, report insufficient_data cleanly without crashing
    if struct_res.status == "insufficient_data":
        logger.info("Validation completed: status=insufficient_data (no MRZ found)")
        return _build_insufficient_data_response(struct_res.message)

    norm_l1 = struct_res.normalized_line1 or ""
    norm_l2 = struct_res.normalized_line2 or ""

    # ─────────────────────────────────────────────────────────────
    # Check 2: Check Digits (ICAO 7-3-1 Modulo 10)
    # ─────────────────────────────────────────────────────────────
    # 2a: Document Number Check Digit (Line 2, pos 0-8 data, pos 9 check digit)
    if len(norm_l2) >= 10:
        doc_num_raw = norm_l2[0:9]
        doc_chk_char = norm_l2[9]
        doc_chk_res = validate_check_digit(doc_num_raw, doc_chk_char, "Document number")
        doc_num_evidence = CheckDigitEvidence(
            status="passed" if doc_chk_res.valid else "failed",
            valid=doc_chk_res.valid,
            computed=doc_chk_res.computed,
            actual=doc_chk_res.actual,
            message=doc_chk_res.message,
        )
        if not doc_chk_res.valid:
            issues.append(
                ValidationIssue(
                    severity="failure",
                    check="document_number_checksum",
                    message=doc_chk_res.message,
                )
            )
    else:
        doc_num_evidence = CheckDigitEvidence(
            status="unknown",
            valid=False,
            computed=0,
            actual=None,
            message="MRZ Line 2 too short to extract document number check digit.",
        )
        issues.append(
            ValidationIssue(
                severity="warning",
                check="document_number_checksum",
                message="MRZ Line 2 too short for document number checksum.",
            )
        )

    # 2b: Date of Birth Check Digit (Line 2, pos 13-18 data, pos 19 check digit)
    if len(norm_l2) >= 20:
        dob_raw = norm_l2[13:19]
        dob_chk_char = norm_l2[19]
        dob_chk_res = validate_check_digit(dob_raw, dob_chk_char, "Date of birth")
        dob_evidence = CheckDigitEvidence(
            status="passed" if dob_chk_res.valid else "failed",
            valid=dob_chk_res.valid,
            computed=dob_chk_res.computed,
            actual=dob_chk_res.actual,
            message=dob_chk_res.message,
        )
        if not dob_chk_res.valid:
            issues.append(
                ValidationIssue(
                    severity="failure",
                    check="dob_checksum",
                    message=dob_chk_res.message,
                )
            )
    else:
        dob_evidence = CheckDigitEvidence(
            status="unknown",
            valid=False,
            computed=0,
            actual=None,
            message="MRZ Line 2 too short to extract date of birth check digit.",
        )
        issues.append(
            ValidationIssue(
                severity="warning",
                check="dob_checksum",
                message="MRZ Line 2 too short for DOB checksum.",
            )
        )

    # 2c: Expiry Date Check Digit (Line 2, pos 21-26 data, pos 27 check digit)
    if len(norm_l2) >= 28:
        exp_raw = norm_l2[21:27]
        exp_chk_char = norm_l2[27]
        exp_chk_res = validate_check_digit(exp_raw, exp_chk_char, "Date of expiry")
        exp_evidence = CheckDigitEvidence(
            status="passed" if exp_chk_res.valid else "failed",
            valid=exp_chk_res.valid,
            computed=exp_chk_res.computed,
            actual=exp_chk_res.actual,
            message=exp_chk_res.message,
        )
        if not exp_chk_res.valid:
            issues.append(
                ValidationIssue(
                    severity="failure",
                    check="expiry_checksum",
                    message=exp_chk_res.message,
                )
            )
    else:
        exp_evidence = CheckDigitEvidence(
            status="unknown",
            valid=False,
            computed=0,
            actual=None,
            message="MRZ Line 2 too short to extract expiry check digit.",
        )
        issues.append(
            ValidationIssue(
                severity="warning",
                check="expiry_checksum",
                message="MRZ Line 2 too short for expiry checksum.",
            )
        )

    # 2d: Composite Check Digit (Line 2, pos 0-9 + pos 13-19 + pos 21-42, check digit at pos 43)
    if len(norm_l2) >= 44:
        # Standard TD3 composite string:
        # pos 0..9 (doc num + chk) + pos 13..19 (dob + chk) + pos 21..42 (exp + chk + opt data + opt chk)
        composite_data = norm_l2[0:10] + norm_l2[13:20] + norm_l2[21:43]
        composite_chk_char = norm_l2[43]
        comp_chk_res = validate_check_digit(composite_data, composite_chk_char, "Composite")
        comp_evidence = CheckDigitEvidence(
            status="passed" if comp_chk_res.valid else "failed",
            valid=comp_chk_res.valid,
            computed=comp_chk_res.computed,
            actual=comp_chk_res.actual,
            message=comp_chk_res.message,
        )
        if not comp_chk_res.valid:
            issues.append(
                ValidationIssue(
                    severity="critical",
                    check="composite_checksum",
                    message=comp_chk_res.message,
                )
            )
    else:
        comp_evidence = CheckDigitEvidence(
            status="unknown",
            valid=False,
            computed=0,
            actual=None,
            message="MRZ Line 2 length insufficient to compute composite check digit.",
        )
        issues.append(
            ValidationIssue(
                severity="warning",
                check="composite_checksum",
                message="MRZ Line 2 incomplete for composite check digit.",
            )
        )

    # ─────────────────────────────────────────────────────────────
    # Check 3: Date Parsing & Expiration Evaluation
    # ─────────────────────────────────────────────────────────────
    parsed_exp_result = None
    if len(norm_l2) >= 27:
        parsed_exp_result = parse_mrz_date(
            norm_l2[21:27],
            is_expiry=True,
            reference_date=reference_date,
            field_name="Date of expiry",
        )
        if not parsed_exp_result.valid:
            issues.append(
                ValidationIssue(
                    severity="failure",
                    check="expiry_date",
                    message=parsed_exp_result.message,
                )
            )

    expiry_eval = validate_expiry(
        parsed_exp_result.parsed_date if parsed_exp_result else None,
        reference_date=reference_date,
    )

    expiry_evidence = ExpiryCheckEvidence(
        status=expiry_eval.status,
        valid=expiry_eval.valid,
        expired=expiry_eval.expired,
        expiry_date=expiry_eval.expiry_date_str,
        message=expiry_eval.message,
    )

    if expiry_eval.expired:
        issues.append(
            ValidationIssue(
                severity="failure",
                check="expiry_date",
                message=expiry_eval.message,
            )
        )

    # ─────────────────────────────────────────────────────────────
    # Check 4: The Passport Number Binding Trap (VIZ <-> MRZ)
    # ─────────────────────────────────────────────────────────────
    viz_doc_num = traveler.docNumber if traveler else None
    mrz_doc_num = norm_l2[0:9].rstrip("<") if len(norm_l2) >= 9 else None

    binding_res = validate_passport_binding(viz_doc_num, mrz_doc_num)
    binding_evidence = PassportBindingEvidence(
        status=binding_res.status,
        valid=binding_res.valid,
        viz_value=binding_res.viz_value,
        mrz_value=binding_res.mrz_value,
        match=binding_res.match,
        message=binding_res.message,
    )

    if binding_res.match is False:
        issues.append(
            ValidationIssue(
                severity="critical",
                check="passport_number_binding",
                message=binding_res.message,
            )
        )

    # ─────────────────────────────────────────────────────────────
    # Check 5: Cross-Zone Field Consistency (VIZ <-> MRZ)
    # ─────────────────────────────────────────────────────────────
    field_checks: dict[str, FieldConsistencyItem] = {}

    # Document number
    field_checks["document_number"] = FieldConsistencyItem(
        viz=binding_res.viz_value,
        mrz=binding_res.mrz_value,
        match=binding_res.match,
        status="match" if binding_res.match is True else ("mismatch" if binding_res.match is False else "unknown"),
        message=binding_res.message,
    )

    # Name
    viz_name = traveler.name if traveler else None
    mrz_name_raw = norm_l1[5:44] if len(norm_l1) >= 5 else None
    name_cmp = compare_name_field(viz_name, mrz_name_raw)
    field_checks["name"] = FieldConsistencyItem(
        viz=name_cmp.viz_value,
        mrz=name_cmp.mrz_value,
        match=name_cmp.match,
        status=name_cmp.status,
        message=name_cmp.message,
    )
    if name_cmp.match is False:
        issues.append(
            ValidationIssue(
                severity="warning",
                check="viz_mrz_consistency",
                message=name_cmp.message,
            )
        )

    # Nationality
    viz_nat = traveler.nationality if traveler else None
    mrz_nat = norm_l2[10:13].rstrip("<") if len(norm_l2) >= 13 else None
    nat_cmp = compare_nationality_field(viz_nat, mrz_nat)
    field_checks["nationality"] = FieldConsistencyItem(
        viz=nat_cmp.viz_value,
        mrz=nat_cmp.mrz_value,
        match=nat_cmp.match,
        status=nat_cmp.status,
        message=nat_cmp.message,
    )
    if nat_cmp.match is False:
        issues.append(
            ValidationIssue(
                severity="warning",
                check="viz_mrz_consistency",
                message=nat_cmp.message,
            )
        )

    # Date of Birth
    viz_dob = traveler.dob if traveler else None
    mrz_dob_iso = None
    if len(norm_l2) >= 19:
        parsed_dob = parse_mrz_date(norm_l2[13:19], is_expiry=False, reference_date=reference_date, field_name="Date of birth")
        mrz_dob_iso = parsed_dob.iso_string

    dob_cmp = compare_date_field(viz_dob, mrz_dob_iso, "Date of birth")
    field_checks["date_of_birth"] = FieldConsistencyItem(
        viz=dob_cmp.viz_value,
        mrz=dob_cmp.mrz_value,
        match=dob_cmp.match,
        status=dob_cmp.status,
        message=dob_cmp.message,
    )
    if dob_cmp.match is False:
        issues.append(
            ValidationIssue(
                severity="warning",
                check="viz_mrz_consistency",
                message=dob_cmp.message,
            )
        )

    # Expiry Date
    viz_exp = traveler.expiry if traveler else None
    mrz_exp_iso = expiry_evidence.expiry_date
    exp_cmp = compare_date_field(viz_exp, mrz_exp_iso, "Date of expiry")
    field_checks["expiry_date"] = FieldConsistencyItem(
        viz=exp_cmp.viz_value,
        mrz=exp_cmp.mrz_value,
        match=exp_cmp.match,
        status=exp_cmp.status,
        message=exp_cmp.message,
    )
    if exp_cmp.match is False:
        issues.append(
            ValidationIssue(
                severity="warning",
                check="viz_mrz_consistency",
                message=exp_cmp.message,
            )
        )

    # Gender
    viz_gender = traveler.gender if traveler else None
    mrz_gender = norm_l2[20] if len(norm_l2) >= 21 else None
    gen_cmp = compare_gender_field(viz_gender, mrz_gender)
    field_checks["gender"] = FieldConsistencyItem(
        viz=gen_cmp.viz_value,
        mrz=gen_cmp.mrz_value,
        match=gen_cmp.match,
        status=gen_cmp.status,
        message=gen_cmp.message,
    )
    if gen_cmp.match is False:
        issues.append(
            ValidationIssue(
                severity="warning",
                check="viz_mrz_consistency",
                message=gen_cmp.message,
            )
        )

    # Consistency report summary
    mismatches = [k for k, v in field_checks.items() if v.status == "mismatch"]
    if mismatches:
        consist_status = "failed" if "document_number" in mismatches else "warning"
        consist_msg = f"Field inconsistencies detected in {len(mismatches)} field(s): {', '.join(mismatches)}."
    else:
        consist_status = "passed"
        consist_msg = "All available fields cross-checked between VIZ and MRZ are consistent."

    consistency_report = VizMrzConsistencyReport(
        status=consist_status,
        fields=field_checks,
        message=consist_msg,
    )

    # ─────────────────────────────────────────────────────────────
    # Final Synthesis: Overall Document Validation Status
    # ─────────────────────────────────────────────────────────────
    has_critical = any(iss.severity == "critical" for iss in issues)
    has_failure = any(iss.severity == "failure" for iss in issues)
    has_warning = any(iss.severity == "warning" for iss in issues)

    if has_critical or has_failure:
        overall_status = "failed"
        summary = (
            "Document validation failed. Inconsistencies or checksum errors "
            "detected in machine-readable zone or cross-field bindings."
        )
    elif has_warning:
        overall_status = "warning"
        summary = (
            "Document validation passed with warnings. Some fields were incomplete "
            "or showed minor formatting discrepancies."
        )
    else:
        overall_status = "passed"
        summary = "Passport MRZ structure, ICAO checksums, and cross-field validation passed successfully."

    # Event-level logging only — NO PII
    logger.info(
        "Passport validation completed: status=%s issues=%d critical=%s failures=%s",
        overall_status,
        len(issues),
        has_critical,
        has_failure,
    )

    return DocumentValidationSummary(
        status=overall_status,
        summary=summary,
        checks=ValidationChecks(
            mrz_structure=mrz_check_item,
            document_number_checksum=doc_num_evidence,
            dob_checksum=dob_evidence,
            expiry_checksum=exp_evidence,
            composite_checksum=comp_evidence,
            expiry_date=expiry_evidence,
            passport_number_binding=binding_evidence,
            viz_mrz_consistency=consistency_report,
        ),
        issues=issues,
    )


def _build_insufficient_data_response(msg: str) -> DocumentValidationSummary:
    """Fallback summary when no MRZ could be detected."""
    empty_chk = CheckDigitEvidence(
        status="unknown",
        valid=False,
        computed=0,
        actual=None,
        message="No MRZ data available to calculate checksum.",
    )
    return DocumentValidationSummary(
        status="insufficient_data",
        summary=msg,
        checks=ValidationChecks(
            mrz_structure=CheckItem(
                status="insufficient_data",
                valid=False,
                message=msg,
            ),
            document_number_checksum=empty_chk,
            dob_checksum=empty_chk,
            expiry_checksum=empty_chk,
            composite_checksum=empty_chk,
            expiry_date=ExpiryCheckEvidence(
                status="unknown",
                valid=False,
                expired=None,
                expiry_date=None,
                message="No MRZ data available to check expiration.",
            ),
            passport_number_binding=PassportBindingEvidence(
                status="unknown",
                valid=True,
                viz_value=None,
                mrz_value=None,
                match=None,
                message="No MRZ data available to verify passport binding.",
            ),
            viz_mrz_consistency=VizMrzConsistencyReport(
                status="unknown",
                fields={},
                message="No MRZ data available to cross-check fields.",
            ),
        ),
        issues=[
            ValidationIssue(
                severity="warning",
                check="mrz_structure",
                message=msg,
            )
        ],
    )
