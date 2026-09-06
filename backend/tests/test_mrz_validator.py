"""
backend/tests/test_mrz_validator.py

Unit tests for MRZ TD3 structural validation, date parsing, and VIZ-MRZ cross-checks.
"""
import datetime
import pytest
from app.services.validation.mrz_validator import (
    normalize_mrz_line,
    validate_td3_structure,
)
from app.services.validation.date_validator import parse_mrz_date, validate_expiry
from app.services.validation.viz_mrz_checker import (
    compare_gender_field,
    compare_name_field,
    compare_nationality_field,
    validate_passport_binding,
)


class TestMrzNormalization:
    def test_strip_and_uppercase(self):
        assert normalize_mrz_line("  p<indmalhotra  ") == "P<INDMALHOTRA"

    def test_spaces_converted_to_filler(self):
        assert normalize_mrz_line("P<IND MALHOTRA") == "P<IND<MALHOTRA"

    def test_none_or_empty(self):
        assert normalize_mrz_line(None) == ""
        assert normalize_mrz_line("") == ""


class TestValidateTd3Structure:
    LINE1_VALID = "P<INDMALHOTRA<<ASHOK<KUMAR<<<<<<<<<<<<<<<<<<"  # 44 chars
    LINE2_VALID = "A1234567<6IND9001011M2912316<<<<<<<<<<<<<<<2"  # 44 chars

    def test_valid_td3_passes(self):
        res = validate_td3_structure(self.LINE1_VALID, self.LINE2_VALID)
        assert res.valid is True
        assert res.status == "passed"
        assert res.line1_length == 44
        assert res.line2_length == 44
        assert len(res.issues) == 0

    def test_both_lines_missing_returns_insufficient_data(self):
        res = validate_td3_structure(None, None)
        assert res.valid is False
        assert res.status == "insufficient_data"

    def test_line_length_mismatch_fails(self):
        short_line = "P<INDMALHOTRA<<ASHOK"
        res = validate_td3_structure(short_line, self.LINE2_VALID)
        assert res.valid is False
        assert any("44 characters" in iss for iss in res.issues)

    def test_invalid_characters_fail(self):
        bad_l1 = "P<INDMALHOTRA$@ASHOK<KUMAR<<<<<<<<<<<<<<<<<<"
        res = validate_td3_structure(bad_l1, self.LINE2_VALID)
        assert res.valid is False
        assert any("invalid characters" in iss for iss in res.issues)

    def test_non_p_document_code_fails(self):
        bad_l1 = "V<INDMALHOTRA<<ASHOK<KUMAR<<<<<<<<<<<<<<<<<<"
        res = validate_td3_structure(bad_l1, self.LINE2_VALID)
        assert res.valid is False
        assert any("begin with 'P'" in iss for iss in res.issues)


class TestDateValidator:
    def test_valid_dob_parsing(self):
        res = parse_mrz_date("900101", is_expiry=False, reference_date=datetime.date(2026, 1, 1))
        assert res.valid is True
        assert res.parsed_date == datetime.date(1990, 1, 1)
        assert res.iso_string == "1990-01-01"

    def test_valid_future_expiry_parsing(self):
        res = parse_mrz_date("291231", is_expiry=True, reference_date=datetime.date(2026, 1, 1))
        assert res.valid is True
        assert res.parsed_date == datetime.date(2029, 12, 31)

    def test_invalid_month_fails(self):
        res = parse_mrz_date("901301", is_expiry=False)
        assert res.valid is False
        assert "month" in res.message

    def test_invalid_calendar_day_fails(self):
        res = parse_mrz_date("230229", is_expiry=False)  # 2023 was not a leap year
        assert res.valid is False
        assert "valid calendar date" in res.message

    def test_expiry_evaluation_active(self):
        active_date = datetime.date(2029, 12, 31)
        res = validate_expiry(active_date, reference_date=datetime.date(2026, 1, 1))
        assert res.valid is True
        assert res.expired is False
        assert res.status == "passed"

    def test_expiry_evaluation_expired(self):
        expired_date = datetime.date(2020, 1, 1)
        res = validate_expiry(expired_date, reference_date=datetime.date(2026, 1, 1))
        assert res.valid is False
        assert res.expired is True
        assert res.status == "failed"
        assert "expired" in res.message


class TestPassportBindingTrap:
    def test_binding_match(self):
        res = validate_passport_binding("A1234567", "A1234567")
        assert res.valid is True
        assert res.status == "passed"
        assert res.match is True

    def test_binding_mismatch_triggers_failure(self):
        res = validate_passport_binding("A1234567", "Z9999999")
        assert res.valid is False
        assert res.status == "failed"
        assert res.match is False
        assert "Binding mismatch" in res.message

    def test_binding_missing_viz_returns_unknown(self):
        res = validate_passport_binding(None, "A1234567")
        assert res.status == "unknown"
        assert res.match is None


class TestFieldConsistency:
    def test_name_tokens_match(self):
        res = compare_name_field("ASHOK KUMAR MALHOTRA", "MALHOTRA<<ASHOK<KUMAR<<<<<<<<<<<<<<<<<<")
        assert res.match is True
        assert res.status == "match"

    def test_nationality_match_code_and_full(self):
        res = compare_nationality_field("INDIAN", "IND")
        assert res.match is True
        assert res.status == "match"

    def test_gender_match(self):
        res = compare_gender_field("Male", "M")
        assert res.match is True
        assert res.status == "match"

    def test_gender_mismatch(self):
        res = compare_gender_field("Female", "M")
        assert res.match is False
        assert res.status == "mismatch"
