"""
backend/app/services/validation/icao_checkdigit.py

ICAO Doc 9303 Modulo 10 with 7-3-1 Weighting Check Digit Calculator.

Standard algorithm for Machine Readable Travel Documents (MRTDs):
- Characters '0'–'9' map to numerical value 0–9
- Characters 'A'–'Z' map to numerical value 10–35
- Filler character '<' maps to numerical value 0
- Other characters map to 0 (with validation failure elsewhere)
- Weights repeat in sequence: 7, 3, 1, 7, 3, 1, ...
- Sum of (char_value * weight) across all characters modulo 10
  produces the check digit (0–9).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# Repeating weight sequence as specified by ICAO Doc 9303 Part 3
ICAO_WEIGHTS = (7, 3, 1)


def char_to_icao_value(char: str) -> int:
    """
    Convert a single character to its ICAO 9303 numerical value.
    - '0'-'9': 0-9
    - 'A'-'Z': 10-35
    - '<': 0
    - Any other character (e.g. punctuation, spaces): 0
    """
    if not char:
        return 0
    c = char.upper()
    if "0" <= c <= "9":
        return ord(c) - ord("0")
    if "A" <= c <= "Z":
        return ord(c) - ord("A") + 10
    if c == "<":
        return 0
    return 0


def calculate_icao_check_digit(input_str: str) -> int:
    """
    Calculate the ICAO Doc 9303 check digit for a string.

    Args:
        input_str: The string over which the check digit is computed
                   (e.g., document number, date of birth, expiry date,
                    or concatenated composite check fields).

    Returns:
        An integer between 0 and 9 inclusive.
    """
    if not input_str:
        return 0

    total = 0
    for idx, char in enumerate(input_str):
        weight = ICAO_WEIGHTS[idx % 3]
        total += char_to_icao_value(char) * weight

    return total % 10


@dataclass(frozen=True)
class CheckDigitResult:
    """Detailed evidence for a check digit validation check."""
    valid: bool
    computed: int
    actual: Optional[int]
    field_name: str
    message: str


def validate_check_digit(
    field_data: str,
    actual_check_digit_char: str | int | None,
    field_name: str = "field",
) -> CheckDigitResult:
    """
    Validate that the check digit character matches the computed ICAO check digit.

    Args:
        field_data: The string data being checked.
        actual_check_digit_char: The check digit extracted from the MRZ
                                 (single character '0'-'9' or int).
        field_name: Human-friendly name for reporting (e.g. "Passport number").

    Returns:
        CheckDigitResult with valid flag, computed and actual values, and explanation.
    """
    computed = calculate_icao_check_digit(field_data)

    if actual_check_digit_char is None:
        return CheckDigitResult(
            valid=False,
            computed=computed,
            actual=None,
            field_name=field_name,
            message=f"{field_name} check digit character is missing from MRZ.",
        )

    str_actual = str(actual_check_digit_char).strip()
    if not str_actual.isdigit():
        return CheckDigitResult(
            valid=False,
            computed=computed,
            actual=None,
            field_name=field_name,
            message=(
                f"{field_name} check digit is invalid character '{str_actual}'; "
                f"expected a digit (computed {computed})."
            ),
        )

    actual_int = int(str_actual)
    is_valid = computed == actual_int

    if is_valid:
        msg = f"{field_name} check digit valid ({computed})."
    else:
        msg = (
            f"{field_name} check digit mismatch: "
            f"MRZ indicates {actual_int}, but computed algorithm yields {computed}."
        )

    return CheckDigitResult(
        valid=is_valid,
        computed=computed,
        actual=actual_int,
        field_name=field_name,
        message=msg,
    )
