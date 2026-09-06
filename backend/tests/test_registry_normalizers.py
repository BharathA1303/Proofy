"""
tests/test_registry_normalizers.py

Unit tests for Module 5 registry field normalization utilities.

Tests cover:
  - Name normalization: uppercase, MRZ fillers, whitespace, punctuation
  - Date normalization: YYYYMMDD, YYMMDD (MRZ), DD/MM/YYYY, invalid dates
  - Document number strict matching (no fuzzy)
  - Nationality normalization
  - Edge cases: None, empty strings, whitespace-only
"""
import pytest

from app.services.registry.normalizers import (
    dates_match,
    document_numbers_match,
    names_match,
    nationalities_match,
    normalize_date,
    normalize_document_number,
    normalize_name,
    normalize_name_tokens,
    normalize_nationality,
)


# ── Name normalization ────────────────────────────────────────────────────────

class TestNormalizeName:
    def test_uppercase(self):
        assert normalize_name("john doe") == "JOHN DOE"

    def test_already_uppercase(self):
        assert normalize_name("JOHN DOE") == "JOHN DOE"

    def test_mixed_case(self):
        assert normalize_name("John Michael Doe") == "JOHN MICHAEL DOE"

    def test_mrz_filler_double_bracket(self):
        """MRZ surname<<given format → tokens separated by spaces"""
        assert normalize_name("DOE<<JOHN<MICHAEL") == "DOE JOHN MICHAEL"

    def test_mrz_filler_single(self):
        assert normalize_name("SMITH<JANE") == "SMITH JANE"

    def test_whitespace_collapse(self):
        assert normalize_name("  ALICE  BOB  ") == "ALICE BOB"

    def test_trailing_leading_whitespace(self):
        assert normalize_name("  ALICE  ") == "ALICE"

    def test_none_input(self):
        assert normalize_name(None) is None

    def test_empty_string(self):
        assert normalize_name("") is None

    def test_whitespace_only(self):
        assert normalize_name("   ") is None

    def test_mrz_fillers_only(self):
        assert normalize_name("<<<") is None

    def test_multiple_mrz_fillers(self):
        assert normalize_name("DOE<<JOHN<<<") == "DOE JOHN"


class TestNormalizeNameTokens:
    def test_basic_tokenization(self):
        tokens = normalize_name_tokens("JOHN DOE")
        assert tokens == frozenset({"JOHN", "DOE"})

    def test_mrz_format_tokenization(self):
        tokens = normalize_name_tokens("DOE<<JOHN")
        assert tokens == frozenset({"DOE", "JOHN"})

    def test_none_returns_none(self):
        assert normalize_name_tokens(None) is None


class TestNamesMatch:
    def test_exact_match(self):
        assert names_match("JOHN DOE", "JOHN DOE") is True

    def test_case_insensitive(self):
        assert names_match("john doe", "JOHN DOE") is True

    def test_mrz_format_vs_display(self):
        """DOE<<JOHN should match JOHN DOE (token normalization)"""
        assert names_match("DOE<<JOHN", "JOHN DOE") is True

    def test_mrz_vs_mrz(self):
        assert names_match("DOE<<JOHN<MICHAEL", "DOE JOHN MICHAEL") is True

    def test_mismatch_different_tokens(self):
        assert names_match("JOHN DOE", "JANE DOE") is False

    def test_mismatch_extra_token(self):
        """Middle name present in one but not the other — NOT a match"""
        assert names_match("JOHN MICHAEL DOE", "JOHN DOE") is False

    def test_none_first(self):
        assert names_match(None, "JOHN DOE") is False

    def test_none_second(self):
        assert names_match("JOHN DOE", None) is False

    def test_both_none(self):
        assert names_match(None, None) is False

    def test_near_match_not_fuzzy(self):
        """A near-match is NOT treated as a match — no Levenshtein"""
        assert names_match("JOHN DOE", "JOHN DOEL") is False


# ── Date normalization ─────────────────────────────────────────────────────────

class TestNormalizeDate:
    def test_yyyymmdd_dashes(self):
        assert normalize_date("1985-06-15") == "1985-06-15"

    def test_yyyymmdd_no_sep(self):
        assert normalize_date("19850615") == "1985-06-15"

    def test_mrz_yymmdd_pre_2000(self):
        """Year >= 30 → 1900s"""
        assert normalize_date("850615") == "1985-06-15"

    def test_mrz_yymmdd_post_2000(self):
        """Year < 30 → 2000s"""
        assert normalize_date("100615") == "2010-06-15"

    def test_mrz_pivot_year_30(self):
        """Year exactly 30 → 1930"""
        assert normalize_date("300101") == "1930-01-01"

    def test_mrz_pivot_year_29(self):
        """Year exactly 29 → 2029"""
        assert normalize_date("290101") == "2029-01-01"

    def test_ddmmyyyy_slash(self):
        assert normalize_date("15/06/1985") == "1985-06-15"

    def test_ddmmyyyy_dash(self):
        assert normalize_date("15-06-1985") == "1985-06-15"

    def test_none_input(self):
        assert normalize_date(None) is None

    def test_invalid_month(self):
        assert normalize_date("1985-13-01") is None

    def test_invalid_day(self):
        assert normalize_date("1985-06-32") is None

    def test_empty_string(self):
        assert normalize_date("") is None

    def test_garbage_string(self):
        assert normalize_date("not-a-date") is None

    def test_leading_whitespace(self):
        assert normalize_date("  1985-06-15  ") == "1985-06-15"


class TestDatesMatch:
    def test_same_format(self):
        assert dates_match("1985-06-15", "1985-06-15") is True

    def test_different_formats(self):
        assert dates_match("850615", "1985-06-15") is True

    def test_mismatch(self):
        assert dates_match("1985-06-15", "1984-06-15") is False

    def test_none_first(self):
        assert dates_match(None, "1985-06-15") is False

    def test_none_second(self):
        assert dates_match("1985-06-15", None) is False


# ── Document number normalization ──────────────────────────────────────────────

class TestNormalizeDocumentNumber:
    def test_uppercase(self):
        assert normalize_document_number("t9876543") == "T9876543"

    def test_strips_whitespace(self):
        assert normalize_document_number("  T9876543  ") == "T9876543"

    def test_removes_internal_spaces(self):
        assert normalize_document_number("T 987 6543") == "T9876543"

    def test_none_input(self):
        assert normalize_document_number(None) is None

    def test_empty_string(self):
        assert normalize_document_number("") is None

    def test_whitespace_only(self):
        assert normalize_document_number("   ") is None


class TestDocumentNumbersMatch:
    def test_exact_match(self):
        assert document_numbers_match("T9876543", "T9876543") is True

    def test_case_normalized(self):
        assert document_numbers_match("t9876543", "T9876543") is True

    def test_strict_no_fuzzy(self):
        """T9876543 must NOT match T9876548 — strict equality only"""
        assert document_numbers_match("T9876543", "T9876548") is False

    def test_strict_one_char_diff(self):
        """One character difference = MISMATCH, never MATCH"""
        assert document_numbers_match("TESTPASS001", "TESTPASS002") is False

    def test_none_first(self):
        assert document_numbers_match(None, "T9876543") is False

    def test_none_second(self):
        assert document_numbers_match("T9876543", None) is False

    def test_both_none(self):
        assert document_numbers_match(None, None) is False


# ── Nationality normalization ──────────────────────────────────────────────────

class TestNormalizationNationality:
    def test_uppercase(self):
        assert normalize_nationality("ind") == "IND"

    def test_strip_whitespace(self):
        assert normalize_nationality("  IND  ") == "IND"

    def test_mrz_filler(self):
        assert normalize_nationality("IND<") == "IND"

    def test_none_input(self):
        assert normalize_nationality(None) is None

    def test_empty(self):
        assert normalize_nationality("") is None


class TestNationalitiesMatch:
    def test_match(self):
        assert nationalities_match("IND", "IND") is True

    def test_case_normalized(self):
        assert nationalities_match("ind", "IND") is True

    def test_mismatch(self):
        assert nationalities_match("IND", "USA") is False

    def test_none_first(self):
        assert nationalities_match(None, "IND") is False
