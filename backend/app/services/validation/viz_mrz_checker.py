"""
backend/app/services/validation/viz_mrz_checker.py

Cross-checks fields between the Visual Inspection Zone (VIZ) and the
Machine Readable Zone (MRZ).

Core capabilities:
- The Passport Number Binding Trap (critical cross-check)
- Field-by-field consistency: Passport number, Name, Nationality, DOB, Expiry, Gender
- Returns explicit states: MATCH, MISMATCH, UNKNOWN
- Never invents data or assumes missing fields are mismatches
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FieldComparison:
    """Evidence for a single field comparison between VIZ and MRZ."""
    field_name: str
    viz_value: Optional[str]
    mrz_value: Optional[str]
    match: Optional[bool]  # True = match, False = mismatch, None = unknown
    status: str            # "match" | "mismatch" | "unknown"
    message: str


@dataclass(frozen=True)
class PassportBindingResult:
    """The Passport Binding Trap verification result."""
    valid: bool
    status: str  # "passed" | "failed" | "unknown"
    viz_value: Optional[str]
    mrz_value: Optional[str]
    match: Optional[bool]
    message: str


def _clean_alphanumeric(val: Optional[str]) -> str:
    """Strip whitespace, punctuation, and MRZ filler characters '<'."""
    if not val:
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(val).upper())


def _normalize_name(name_str: Optional[str]) -> list[str]:
    """
    Split name into sorted non-empty uppercase word tokens.
    Replaces MRZ filler '<' and punctuation with spaces.
    """
    if not name_str:
        return []
    cleaned = re.sub(r"[<,\.\-_/]+", " ", str(name_str).upper())
    tokens = [t.strip() for t in cleaned.split() if t.strip()]
    return sorted(tokens)


def _normalize_date_to_dmy(date_str: Optional[str]) -> Optional[tuple[int, int, int]]:
    """
    Try to extract (day, month, year) integers from various date formats:
    - DD/MM/YYYY or DD-MM-YYYY
    - YYYY-MM-DD
    - DD/MM/YY
    """
    if not date_str:
        return None
    s = str(date_str).strip()

    # YYYY-MM-DD
    m = re.match(r"^(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})$", s)
    if m:
        return (int(m.group(3)), int(m.group(2)), int(m.group(1)))

    # DD/MM/YYYY
    m = re.match(r"^(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})$", s)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # DD/MM/YY
    m = re.match(r"^(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2})$", s)
    if m:
        yy = int(m.group(3))
        # Default century: 2000s if < 50 else 1900s
        year = 2000 + yy if yy < 50 else 1900 + yy
        return (int(m.group(1)), int(m.group(2)), year)

    return None


def validate_passport_binding(
    viz_doc_number: Optional[str],
    mrz_doc_number: Optional[str],
) -> PassportBindingResult:
    """
    Execute the Passport Binding Trap:
    Cross-checks the document number from the Visual Zone against the MRZ.

    A mismatch between the visual document number and the machine-readable number
    is a primary signal of physical alteration (e.g. text substitution).

    Returns:
        PassportBindingResult with explicit match flag and evidence.
    """
    clean_viz = _clean_alphanumeric(viz_doc_number)
    clean_mrz = _clean_alphanumeric(mrz_doc_number)

    if not clean_viz or not clean_mrz:
        return PassportBindingResult(
            valid=True,  # Does not hard-fail if one zone was unreadable
            status="unknown",
            viz_value=viz_doc_number,
            mrz_value=mrz_doc_number,
            match=None,
            message=(
                "Passport number binding could not be verified: "
                f"VIZ is {'present' if clean_viz else 'missing'}, "
                f"MRZ is {'present' if clean_mrz else 'missing'}."
            ),
        )

    if clean_viz == clean_mrz:
        return PassportBindingResult(
            valid=True,
            status="passed",
            viz_value=viz_doc_number,
            mrz_value=mrz_doc_number,
            match=True,
            message="Passport number in Visual Inspection Zone binds with MRZ.",
        )

    return PassportBindingResult(
        valid=False,
        status="failed",
        viz_value=viz_doc_number,
        mrz_value=mrz_doc_number,
        match=False,
        message=(
            f"Binding mismatch: Visual document number '{viz_doc_number}' "
            f"does not match MRZ document number '{mrz_doc_number}'."
        ),
    )


def compare_text_field(
    viz_val: Optional[str],
    mrz_val: Optional[str],
    field_name: str,
) -> FieldComparison:
    """Generic text cross-check."""
    clean_viz = _clean_alphanumeric(viz_val)
    clean_mrz = _clean_alphanumeric(mrz_val)

    if not clean_viz or not clean_mrz:
        return FieldComparison(
            field_name=field_name,
            viz_value=viz_val,
            mrz_value=mrz_val,
            match=None,
            status="unknown",
            message=f"{field_name} unavailable in one or both zones for comparison.",
        )

    if clean_viz == clean_mrz:
        return FieldComparison(
            field_name=field_name,
            viz_value=viz_val,
            mrz_value=mrz_val,
            match=True,
            status="match",
            message=f"{field_name} matches across VIZ and MRZ.",
        )

    return FieldComparison(
        field_name=field_name,
        viz_value=viz_val,
        mrz_value=mrz_val,
        match=False,
        status="mismatch",
        message=f"{field_name} mismatch: VIZ has '{viz_val}', MRZ has '{mrz_val}'.",
    )


def compare_name_field(
    viz_name: Optional[str],
    mrz_name: Optional[str],
) -> FieldComparison:
    """
    Compare traveler name across VIZ and MRZ using token-set comparison.
    MRZ names have format: SURNAME<<GIVEN<NAMES<<<<
    VIZ names have format: GIVEN NAMES SURNAME or SURNAME, GIVEN NAMES
    """
    viz_tokens = _normalize_name(viz_name)
    mrz_tokens = _normalize_name(mrz_name)

    if not viz_tokens or not mrz_tokens:
        return FieldComparison(
            field_name="name",
            viz_value=viz_name,
            mrz_value=mrz_name,
            match=None,
            status="unknown",
            message="Holder name is unavailable in one or both zones for comparison.",
        )

    set_viz = set(viz_tokens)
    set_mrz = set(mrz_tokens)

    # If sets are equal, or one is a subset of the other (e.g. middle name omitted in VIZ)
    if set_viz == set_mrz:
        return FieldComparison(
            field_name="name",
            viz_value=viz_name,
            mrz_value=mrz_name,
            match=True,
            status="match",
            message="Holder name matches across VIZ and MRZ.",
        )

    intersection = set_viz.intersection(set_mrz)
    # If the major components match (at least 50% overlap or surname matches)
    if len(intersection) >= min(len(set_viz), len(set_mrz)) and len(intersection) > 0:
        return FieldComparison(
            field_name="name",
            viz_value=viz_name,
            mrz_value=mrz_name,
            match=True,
            status="match",
            message="Holder name components align across VIZ and MRZ.",
        )

    # Check if all viz tokens exist in mrz string (handles cases where OCR merged consecutive fillers between names)
    combined_mrz = "".join(mrz_tokens)
    combined_viz = "".join(viz_tokens)
    if all(tok in combined_mrz for tok in viz_tokens) or all(tok in combined_viz for tok in mrz_tokens):
        return FieldComparison(
            field_name="name",
            viz_value=viz_name,
            mrz_value=mrz_name,
            match=True,
            status="match",
            message="Holder name components align across VIZ and MRZ.",
        )

    return FieldComparison(
        field_name="name",
        viz_value=viz_name,
        mrz_value=mrz_name,
        match=False,
        status="mismatch",
        message=f"Holder name mismatch: VIZ '{viz_name}' does not match MRZ '{mrz_name}'.",
    )


def compare_date_field(
    viz_date: Optional[str],
    mrz_date: Optional[str],
    field_name: str,
) -> FieldComparison:
    """Compare a date field across VIZ and MRZ by calendar components."""
    dmy_viz = _normalize_date_to_dmy(viz_date)
    dmy_mrz = _normalize_date_to_dmy(mrz_date)

    if not dmy_viz or not dmy_mrz:
        # Fallback to alphanumeric comparison if format didn't parse
        return compare_text_field(viz_date, mrz_date, field_name)

    if dmy_viz == dmy_mrz:
        return FieldComparison(
            field_name=field_name,
            viz_value=viz_date,
            mrz_value=mrz_date,
            match=True,
            status="match",
            message=f"{field_name} matches across VIZ and MRZ.",
        )

    return FieldComparison(
        field_name=field_name,
        viz_value=viz_date,
        mrz_value=mrz_date,
        match=False,
        status="mismatch",
        message=f"{field_name} mismatch: VIZ has '{viz_date}', MRZ has '{mrz_date}'.",
    )


def compare_gender_field(
    viz_gender: Optional[str],
    mrz_gender: Optional[str],
) -> FieldComparison:
    """Compare gender/sex field."""
    g_viz = _clean_alphanumeric(viz_gender)
    g_mrz = _clean_alphanumeric(mrz_gender)

    if not g_viz or not g_mrz:
        return FieldComparison(
            field_name="gender",
            viz_value=viz_gender,
            mrz_value=mrz_gender,
            match=None,
            status="unknown",
            message="Gender is unavailable in one or both zones.",
        )

    # Standardize to 1st char (M / F / X)
    c_viz = g_viz[0] if g_viz else ""
    c_mrz = g_mrz[0] if g_mrz else ""

    if c_viz == c_mrz:
        return FieldComparison(
            field_name="gender",
            viz_value=viz_gender,
            mrz_value=mrz_gender,
            match=True,
            status="match",
            message="Gender matches across VIZ and MRZ.",
        )

    return FieldComparison(
        field_name="gender",
        viz_value=viz_gender,
        mrz_value=mrz_gender,
        match=False,
        status="mismatch",
        message=f"Gender mismatch: VIZ has '{viz_gender}', MRZ has '{mrz_gender}'.",
    )


def compare_nationality_field(
    viz_nat: Optional[str],
    mrz_nat: Optional[str],
) -> FieldComparison:
    """
    Compare nationality across VIZ and MRZ.
    Handles ISO 3-letter codes vs full country names (e.g. IND vs INDIAN).
    """
    c_viz = _clean_alphanumeric(viz_nat)
    c_mrz = _clean_alphanumeric(mrz_nat)

    if not c_viz or not c_mrz:
        return FieldComparison(
            field_name="nationality",
            viz_value=viz_nat,
            mrz_value=mrz_nat,
            match=None,
            status="unknown",
            message="Nationality unavailable in one or both zones.",
        )

    # Direct match or prefix match (e.g., 'IND' in 'INDIAN' or vice versa)
    if c_viz == c_mrz or c_viz.startswith(c_mrz) or c_mrz.startswith(c_viz):
        return FieldComparison(
            field_name="nationality",
            viz_value=viz_nat,
            mrz_value=mrz_nat,
            match=True,
            status="match",
            message="Nationality matches across VIZ and MRZ.",
        )

    return FieldComparison(
        field_name="nationality",
        viz_value=viz_nat,
        mrz_value=mrz_nat,
        match=False,
        status="mismatch",
        message=f"Nationality mismatch: VIZ has '{viz_nat}', MRZ has '{mrz_nat}'.",
    )
