"""
backend/app/services/validation/date_validator.py

Validates and parses dates extracted from MRZ and Visual Inspection Zone.

Handles:
- ICAO Doc 9303 YYMMDD calendar date representation
- Robust century pivot strategy for DOB vs Expiry dates
- Strict calendar date validation (leap years, month bounds, day bounds)
- Expiry status evaluation relative to reference date (default: today)
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DateValidationResult:
    """Outcome of parsing and validating an MRZ date field."""
    valid: bool
    parsed_date: Optional[datetime.date]
    iso_string: Optional[str]
    raw_yymmdd: str
    field_name: str
    message: str


@dataclass(frozen=True)
class ExpiryValidationResult:
    """Outcome of evaluating document expiration."""
    valid: bool
    expired: Optional[bool]
    status: str  # "passed" | "failed" | "unknown"
    expiry_date: Optional[datetime.date]
    expiry_date_str: Optional[str]
    reference_date_str: str
    message: str


@dataclass(frozen=True)
class ValidityPeriodResult:
    """Outcome of evaluating the issue-to-expiry validity window."""
    valid: bool
    status: str  # "passed" | "warning" | "unknown"
    issue_date_str: Optional[str]
    expiry_date_str: Optional[str]
    validity_years: Optional[float]
    exceeds_standard_term: bool
    message: str


# Standard adult Indian passport validity window (ICAO-permitted maximum).
MAX_STANDARD_VALIDITY_YEARS = 10


def parse_mrz_date(
    yymmdd: Optional[str],
    is_expiry: bool = False,
    reference_date: Optional[datetime.date] = None,
    field_name: str = "Date",
) -> DateValidationResult:
    """
    Parse a 6-digit YYMMDD string into a valid calendar date according to ICAO rules.

    Century Interpretation Strategy:
    - Reference date defaults to today's date.
    - For Date of Birth (is_expiry=False):
        Persons holding travel documents are typically under 110 years old and born before today.
        If 2000 + YY <= reference_date.year:
            year = 2000 + YY
        Else:
            year = 1900 + YY
        If the resulting date is still in the future relative to reference_date:
            year = 1900 + YY
    - For Expiry Date (is_expiry=True):
        Machine-readable passports are valid for at most 10-15 years.
        All contemporary active and recently expired MRTDs fall in the 2000-2099 century:
            year = 2000 + YY

    Returns:
        DateValidationResult with parsed date or specific calendar error.
    """
    if reference_date is None:
        reference_date = datetime.date.today()

    if not yymmdd or not str(yymmdd).strip():
        return DateValidationResult(
            valid=False,
            parsed_date=None,
            iso_string=None,
            raw_yymmdd="",
            field_name=field_name,
            message=f"{field_name} string is missing or empty.",
        )

    raw = str(yymmdd).strip()

    if len(raw) != 6 or not raw.isdigit():
        return DateValidationResult(
            valid=False,
            parsed_date=None,
            iso_string=None,
            raw_yymmdd=raw,
            field_name=field_name,
            message=f"{field_name} '{raw}' is not a valid 6-digit YYMMDD string.",
        )

    yy = int(raw[0:2])
    mm = int(raw[2:4])
    dd = int(raw[4:6])

    # Basic month check
    if mm < 1 or mm > 12:
        return DateValidationResult(
            valid=False,
            parsed_date=None,
            iso_string=None,
            raw_yymmdd=raw,
            field_name=field_name,
            message=f"{field_name} has invalid calendar month: {mm:02d} (must be 01-12).",
        )

    # Century determination
    if is_expiry:
        year = 2000 + yy
    else:
        # Date of birth
        if (2000 + yy) <= reference_date.year:
            year = 2000 + yy
        else:
            year = 1900 + yy

    # Validate full calendar date (checks leap years, 30 vs 31 days, etc.)
    try:
        parsed = datetime.date(year, mm, dd)
    except ValueError as exc:
        return DateValidationResult(
            valid=False,
            parsed_date=None,
            iso_string=None,
            raw_yymmdd=raw,
            field_name=field_name,
            message=f"{field_name} is not a valid calendar date ({raw}): {exc}.",
        )

    # Logical check: DOB cannot be in the future
    if not is_expiry and parsed > reference_date:
        # Check if shifting century to 1900 makes it valid
        try:
            alt_parsed = datetime.date(1900 + yy, mm, dd)
            parsed = alt_parsed
        except ValueError:
            return DateValidationResult(
                valid=False,
                parsed_date=None,
                iso_string=None,
                raw_yymmdd=raw,
                field_name=field_name,
                message=f"{field_name} ({parsed.isoformat()}) cannot be in the future.",
            )

    iso_str = parsed.isoformat()
    return DateValidationResult(
        valid=True,
        parsed_date=parsed,
        iso_string=iso_str,
        raw_yymmdd=raw,
        field_name=field_name,
        message=f"{field_name} parsed successfully as {iso_str}.",
    )


def validate_expiry(
    expiry_date: Optional[datetime.date],
    reference_date: Optional[datetime.date] = None,
) -> ExpiryValidationResult:
    """
    Check whether the passport has expired relative to the reference date.

    Note: An expired passport is a document validity issue, not evidence
    of tampering or fraud.
    """
    if reference_date is None:
        reference_date = datetime.date.today()

    ref_str = reference_date.isoformat()

    if expiry_date is None:
        return ExpiryValidationResult(
            valid=False,
            expired=None,
            status="unknown",
            expiry_date=None,
            expiry_date_str=None,
            reference_date_str=ref_str,
            message="Document expiry date could not be determined from available data.",
        )

    exp_str = expiry_date.isoformat()
    is_expired = expiry_date < reference_date

    if is_expired:
        return ExpiryValidationResult(
            valid=False,
            expired=True,
            status="failed",
            expiry_date=expiry_date,
            expiry_date_str=exp_str,
            reference_date_str=ref_str,
            message=f"Passport expired on {exp_str} (current reference date: {ref_str}).",
        )

    return ExpiryValidationResult(
        valid=True,
        expired=False,
        status="passed",
        expiry_date=expiry_date,
        expiry_date_str=exp_str,
        reference_date_str=ref_str,
        message=f"Passport is valid through {exp_str}.",
    )


def validate_validity_period(
    issue_date: Optional[datetime.date],
    expiry_date: Optional[datetime.date],
) -> ValidityPeriodResult:
    """
    Check that issueDate < expiryDate and flag (without hard-failing) when the
    issue-to-expiry span exceeds the standard 10-year adult passport term.

    Shorter-validity documents (minor passports, typically 5 years) are normal
    and must NOT be flagged — only spans exceeding the 10-year maximum are.
    """
    if issue_date is None or expiry_date is None:
        return ValidityPeriodResult(
            valid=True,  # does not hard-fail when one date is unreadable
            status="unknown",
            issue_date_str=issue_date.isoformat() if issue_date else None,
            expiry_date_str=expiry_date.isoformat() if expiry_date else None,
            validity_years=None,
            exceeds_standard_term=False,
            message=(
                "Validity period could not be evaluated: "
                f"issue date is {'present' if issue_date else 'missing'}, "
                f"expiry date is {'present' if expiry_date else 'missing'}."
            ),
        )

    issue_str = issue_date.isoformat()
    exp_str = expiry_date.isoformat()

    if expiry_date <= issue_date:
        return ValidityPeriodResult(
            valid=False,
            status="warning",
            issue_date_str=issue_str,
            expiry_date_str=exp_str,
            validity_years=None,
            exceeds_standard_term=False,
            message=f"Date of issue ({issue_str}) is not before date of expiry ({exp_str}).",
        )

    span_days = (expiry_date - issue_date).days
    validity_years = round(span_days / 365.25, 2)
    exceeds = validity_years > MAX_STANDARD_VALIDITY_YEARS

    if exceeds:
        return ValidityPeriodResult(
            valid=True,
            status="warning",
            issue_date_str=issue_str,
            expiry_date_str=exp_str,
            validity_years=validity_years,
            exceeds_standard_term=True,
            message=(
                f"Validity period of {validity_years} years exceeds the standard "
                f"{MAX_STANDARD_VALIDITY_YEARS}-year adult passport term."
            ),
        )

    return ValidityPeriodResult(
        valid=True,
        status="passed",
        issue_date_str=issue_str,
        expiry_date_str=exp_str,
        validity_years=validity_years,
        exceeds_standard_term=False,
        message=f"Validity period of {validity_years} years is within the standard term.",
    )
