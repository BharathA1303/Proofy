"""
backend/tests/test_icao_checkdigit.py

Unit tests for ICAO Doc 9303 modulo-10 7-3-1 check digit calculator.
Deterministic test vectors directly from ICAO specifications.
"""
import pytest
from app.services.validation.icao_checkdigit import (
    calculate_icao_check_digit,
    char_to_icao_value,
    validate_check_digit,
)


class TestCharToIcaoValue:
    """Test individual character conversions."""

    def test_digits_map_to_themselves(self):
        for d in range(10):
            assert char_to_icao_value(str(d)) == d

    def test_letters_map_to_10_through_35(self):
        assert char_to_icao_value("A") == 10
        assert char_to_icao_value("B") == 11
        assert char_to_icao_value("Z") == 35

    def test_filler_char_maps_to_zero(self):
        assert char_to_icao_value("<") == 0

    def test_case_insensitivity(self):
        assert char_to_icao_value("a") == 10
        assert char_to_icao_value("z") == 35

    def test_empty_or_special_chars_map_to_zero(self):
        assert char_to_icao_value("") == 0
        assert char_to_icao_value(" ") == 0
        assert char_to_icao_value("-") == 0


class TestCalculateIcaoCheckDigit:
    """Deterministic ICAO Doc 9303 test vectors."""

    def test_official_icao_doc_number(self):
        # ICAO Doc 9303 Part 4 sample: 'L898902C3' -> 6
        assert calculate_icao_check_digit("L898902C3") == 6

    def test_official_icao_dob(self):
        # 12 August 1974 -> '740812' -> 2
        assert calculate_icao_check_digit("740812") == 2

    def test_official_icao_expiry(self):
        # 15 April 2012 -> '120415' -> 9
        assert calculate_icao_check_digit("120415") == 9

    def test_official_icao_optional_data(self):
        # 'ZE184226B<<<<<<' -> 1
        assert calculate_icao_check_digit("ZE184226B<<<<<<") == 1

    def test_all_zeros_yields_zero(self):
        assert calculate_icao_check_digit("000000") == 0

    def test_all_fillers_yields_zero(self):
        assert calculate_icao_check_digit("<<<<<<<<<") == 0

    def test_empty_string_yields_zero(self):
        assert calculate_icao_check_digit("") == 0

    def test_weights_cycle_7_3_1(self):
        # Single char '1' at pos 0: 1 * 7 = 7
        assert calculate_icao_check_digit("1") == 7
        # Two chars '11': pos 0: 1*7=7, pos 1: 1*3=3 -> 10 % 10 = 0
        assert calculate_icao_check_digit("11") == 0
        # Three chars '111': 7 + 3 + 1 = 11 % 10 = 1
        assert calculate_icao_check_digit("111") == 1
        # Four chars '1111': 7 + 3 + 1 + 7 = 18 % 10 = 8
        assert calculate_icao_check_digit("1111") == 8


class TestValidateCheckDigit:
    """Test check digit validation helper."""

    def test_matching_digit_returns_valid(self):
        res = validate_check_digit("L898902C3", "6", "Doc number")
        assert res.valid is True
        assert res.computed == 6
        assert res.actual == 6
        assert "valid" in res.message

    def test_mismatched_digit_returns_invalid(self):
        res = validate_check_digit("L898902C3", "7", "Doc number")
        assert res.valid is False
        assert res.computed == 6
        assert res.actual == 7
        assert "mismatch" in res.message

    def test_non_digit_actual_returns_invalid(self):
        res = validate_check_digit("L898902C3", "<", "Doc number")
        assert res.valid is False
        assert res.actual is None
        assert "invalid character" in res.message

    def test_none_actual_returns_invalid(self):
        res = validate_check_digit("L898902C3", None, "Doc number")
        assert res.valid is False
        assert res.actual is None
        assert "missing" in res.message
