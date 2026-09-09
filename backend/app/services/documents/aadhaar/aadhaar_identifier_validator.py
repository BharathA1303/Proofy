"""
backend/app/services/documents/aadhaar/aadhaar_identifier_validator.py

Identifier validator for UIDAI Aadhaar cards.
Implements:
1. Normalization (whitespace/hyphen stripping).
2. Verhoeff D5 Checksum calculation & validation.
3. Sensitive identifier masking (e.g. XXXX XXXX 9012).
4. Ambiguous identifier detection without silent character conversion.
"""
from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Dihedral group D5 multiplication table
VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]

# Permutation table
VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]

# Inverse table
VERHOEFF_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


class ChecksumStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


def compute_verhoeff_check_digit(number_str: str) -> str:
    """Compute the Verhoeff check digit for a given numeric string."""
    clean = re.sub(r"\D", "", number_str)
    c = 0
    for i, ch in enumerate(reversed(clean)):
        c = VERHOEFF_D[c][VERHOEFF_P[(i + 1) % 8][int(ch)]]
    return str(VERHOEFF_INV[c])


def generate_valid_aadhaar(prefix_11: str) -> str:
    """
    Generate a 12-digit Aadhaar number with a valid Verhoeff check digit.
    Prefix must be 11 numeric digits.
    """
    clean = re.sub(r"\D", "", prefix_11)
    if len(clean) != 11:
        raise ValueError("Prefix must contain exactly 11 digits.")
    check_digit = compute_verhoeff_check_digit(clean)
    return clean + check_digit


def validate_verhoeff_checksum(number_str: str) -> ChecksumStatus:
    """
    Validate the Verhoeff checksum of an Aadhaar number string.
    Returns PASS, FAIL, or INCONCLUSIVE.
    """
    if not number_str or not isinstance(number_str, str):
        return ChecksumStatus.INCONCLUSIVE

    clean = number_str.strip()
    if not clean.isdigit() or len(clean) != 12:
        return ChecksumStatus.INCONCLUSIVE

    c = 0
    for i, ch in enumerate(reversed(clean)):
        c = VERHOEFF_D[c][VERHOEFF_P[i % 8][int(ch)]]

    return ChecksumStatus.PASS if c == 0 else ChecksumStatus.FAIL


def mask_aadhaar(raw_id: Optional[str]) -> str:
    """
    Mask an Aadhaar number for privacy.
    Example: '1234 5678 9012' -> 'XXXX XXXX 9012'.
    Never outputs the full 12 digits.
    """
    if not raw_id:
        return ""
    clean = re.sub(r"[\s\-]", "", str(raw_id))
    if len(clean) >= 4:
        last4 = clean[-4:]
        return f"XXXX XXXX {last4}"
    return "XXXX XXXX XXXX"


# Backward compatibility alias used by mock_national_id import chain
mask_national_id = mask_aadhaar


def normalize_aadhaar(raw_id: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Normalize Aadhaar string.
    Returns (normalized_12_digits, error_reason).
    If characters look ambiguous (e.g. letters in place of numbers),
    returns (None, "AMBIGUOUS_IDENTIFIER") rather than guessing.
    """
    if not raw_id or not isinstance(raw_id, str):
        return None, "EMPTY_IDENTIFIER"

    cleaned = raw_id.strip()
    # Check for ambiguous characters (common OCR confusion characters)
    alpha_chars = set(re.findall(r"[A-Za-z]", cleaned))
    if alpha_chars:
        return None, "AMBIGUOUS_IDENTIFIER"

    # Strip spaces and dashes
    digits = re.sub(r"[\s\-]", "", cleaned)

    if not digits.isdigit():
        return None, "NON_NUMERIC_IDENTIFIER"

    if len(digits) != 12:
        return digits, "INVALID_LENGTH"

    # UIDAI standard: Aadhaar numbers cannot start with 0 or 1
    if digits.startswith("0") or digits.startswith("1"):
        return digits, "INVALID_FIRST_DIGIT"

    return digits, None


# Backward compatibility alias
normalize_national_id = normalize_aadhaar
