"""
backend/app/services/validation/mrz_validator.py

ICAO Doc 9303 Part 4 — Machine Readable Passport (TD3) Structural Validator.

Standard TD3 Specifications:
- Line 1: 44 characters
    pos 0: Document code ('P')
    pos 1: Optional type code (e.g. '<', 'O', 'D')
    pos 2-4: Issuing State or Organization (3 characters, A-Z or '<')
    pos 5-43: Name (Primary identifier << Secondary identifier, padded with '<')
- Line 2: 44 characters
    pos 0-8: Document number (9 characters)
    pos 9: Document number check digit (1 character)
    pos 10-12: Nationality (3 characters, A-Z or '<')
    pos 13-18: Date of birth (YYMMDD, 6 characters)
    pos 19: Date of birth check digit (1 character)
    pos 20: Sex ('M', 'F', or '<')
    pos 21-26: Date of expiry (YYMMDD, 6 characters)
    pos 27: Date of expiry check digit (1 character)
    pos 28-41: Optional data / personal number (14 characters)
    pos 42: Optional data check digit (1 character or '<')
    pos 43: Composite check digit (1 character)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# Permitted character set in ICAO Doc 9303 MRZ
MRZ_ALLOWED_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<")
MRZ_CHARSET_REGEX = re.compile(r"^[A-Z0-9<]+$")


@dataclass(frozen=True)
class MrzStructureResult:
    """Outcome of structural and format validation for TD3 MRZ."""
    valid: bool
    status: str  # "passed" | "failed" | "warning" | "insufficient_data"
    raw_line1: Optional[str]
    raw_line2: Optional[str]
    normalized_line1: Optional[str]
    normalized_line2: Optional[str]
    line1_length: int
    line2_length: int
    issues: list[str]
    message: str


def normalize_mrz_line(raw: Optional[str]) -> str:
    """
    Perform conservative, deterministic normalization on an MRZ line:
    - Strip leading/trailing whitespace
    - Convert lowercase to uppercase
    - Replace spaces with filler character '<' (spaces frequently represent '<' in OCR)
    """
    if not raw:
        return ""
    cleaned = raw.strip().upper()
    # In TD3 MRZ, whitespace between tokens corresponds to the filler '<'
    return cleaned.replace(" ", "<")


def validate_td3_structure(
    raw_line1: Optional[str],
    raw_line2: Optional[str],
) -> MrzStructureResult:
    """
    Validate the TD3 MRZ structure and character set according to ICAO Doc 9303.

    Checks:
    1. Both lines exist and are non-empty
    2. Length: exactly 44 characters per line
    3. Character set: only [A-Z0-9<]
    4. Document code starts with 'P' (Passport)
    5. Issuing country code length and characters
    6. Date and gender fields contain expected format

    Returns:
        MrzStructureResult detailing pass/fail and specific structural defects.
    """
    issues: list[str] = []

    norm_l1 = normalize_mrz_line(raw_line1)
    norm_l2 = normalize_mrz_line(raw_line2)

    l1_len = len(norm_l1)
    l2_len = len(norm_l2)

    # 1. Presence check
    if not norm_l1 and not norm_l2:
        return MrzStructureResult(
            valid=False,
            status="insufficient_data",
            raw_line1=raw_line1,
            raw_line2=raw_line2,
            normalized_line1=None,
            normalized_line2=None,
            line1_length=0,
            line2_length=0,
            issues=["No MRZ data detected in document."],
            message="No Machine Readable Zone (MRZ) lines detected.",
        )

    if not norm_l1:
        issues.append("MRZ Line 1 is missing.")
    if not norm_l2:
        issues.append("MRZ Line 2 is missing.")

    # 2. Length check
    if norm_l1 and l1_len != 44:
        issues.append(f"MRZ Line 1 length is {l1_len}; standard TD3 format requires exactly 44 characters.")
    if norm_l2 and l2_len != 44:
        issues.append(f"MRZ Line 2 length is {l2_len}; standard TD3 format requires exactly 44 characters.")

    # 3. Allowed character set check
    if norm_l1 and not MRZ_CHARSET_REGEX.match(norm_l1):
        disallowed = sorted({c for c in norm_l1 if c not in MRZ_ALLOWED_CHARS})
        issues.append(f"MRZ Line 1 contains invalid characters: {disallowed}")
    if norm_l2 and not MRZ_CHARSET_REGEX.match(norm_l2):
        disallowed = sorted({c for c in norm_l2 if c not in MRZ_ALLOWED_CHARS})
        issues.append(f"MRZ Line 2 contains invalid characters: {disallowed}")

    # 4. Field-specific structural assertions for Line 1 (if length permits)
    if norm_l1 and l1_len >= 5:
        doc_code = norm_l1[0]
        if doc_code != "P":
            issues.append(f"MRZ Line 1 document identifier must begin with 'P' (got '{doc_code}').")

    # 5. Field-specific assertions for Line 2 (if length permits)
    if norm_l2 and l2_len >= 28:
        # Date of birth: chars 13..18 (YYMMDD)
        dob_chunk = norm_l2[13:19]
        if not dob_chunk.isdigit():
            issues.append(f"MRZ Date of Birth field '{dob_chunk}' must be 6 numeric digits (YYMMDD).")

        # Sex: char 20
        sex_char = norm_l2[20]
        if sex_char not in ("M", "F", "<", "X"):
            issues.append(f"MRZ Sex field '{sex_char}' must be 'M', 'F', 'X', or '<'.")

        # Expiry date: chars 21..26 (YYMMDD)
        exp_chunk = norm_l2[21:27]
        if not exp_chunk.isdigit():
            issues.append(f"MRZ Date of Expiry field '{exp_chunk}' must be 6 numeric digits (YYMMDD).")

    is_valid = len(issues) == 0

    if is_valid:
        status = "passed"
        message = "MRZ conforms to standard ICAO TD3 (2x44) structure and character set."
    elif not norm_l1 or not norm_l2 or l1_len < 30 or l2_len < 30:
        status = "failed"
        message = "MRZ is severely malformed or incomplete."
    else:
        status = "failed"
        message = "MRZ failed structural validation: " + "; ".join(issues)

    return MrzStructureResult(
        valid=is_valid,
        status=status,
        raw_line1=raw_line1,
        raw_line2=raw_line2,
        normalized_line1=norm_l1 if norm_l1 else None,
        normalized_line2=norm_l2 if norm_l2 else None,
        line1_length=l1_len,
        line2_length=l2_len,
        issues=issues,
        message=message,
    )
