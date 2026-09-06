"""
backend/tests/test_national_id_identifier.py

Tests for National ID Identifier Validator:
- Verhoeff D5 algorithm correctness
- Sensitive identifier masking
- Ambiguous character handling (e.g. 1234 56B8 9012)
- Normalization and validation status outcomes
"""
import pytest
from app.services.documents.national_id.national_id_identifier_validator import (
    ChecksumStatus,
    compute_verhoeff_check_digit,
    generate_valid_national_id,
    mask_national_id,
    normalize_national_id,
    validate_verhoeff_checksum,
)


class TestNationalIdIdentifier:
    def test_verhoeff_algorithm_known_vectors(self):
        # Known test vectors for Verhoeff check digit
        assert compute_verhoeff_check_digit("236") == "3"
        assert validate_verhoeff_checksum("2363") == ChecksumStatus.INCONCLUSIVE  # Length != 12

        # 11-digit prefix -> 12-digit number
        prefix = "98765432109"
        check_digit = compute_verhoeff_check_digit(prefix)
        full_12 = prefix + check_digit
        assert len(full_12) == 12
        assert validate_verhoeff_checksum(full_12) == ChecksumStatus.PASS

    def test_generate_valid_national_id(self):
        valid_id = generate_valid_national_id("54321678901")
        assert len(valid_id) == 12
        assert validate_verhoeff_checksum(valid_id) == ChecksumStatus.PASS

    def test_verhoeff_checksum_failure(self):
        valid_id = generate_valid_national_id("98765432109")
        # Mutate the last digit
        last_digit = int(valid_id[-1])
        corrupted_last = str((last_digit + 1) % 10)
        corrupted_id = valid_id[:-1] + corrupted_last
        assert validate_verhoeff_checksum(corrupted_id) == ChecksumStatus.FAIL

    def test_verhoeff_transposition_error_detection(self):
        # Verhoeff reliably detects all single adjacent transpositions
        valid_id = generate_valid_national_id("23456789012")
        # Swap two adjacent digits in the middle
        transposed = valid_id[:4] + valid_id[5] + valid_id[4] + valid_id[6:]
        assert validate_verhoeff_checksum(transposed) == ChecksumStatus.FAIL

    def test_mask_national_id(self):
        assert mask_national_id("1234 5678 9012") == "XXXX XXXX 9012"
        assert mask_national_id("987654321098") == "XXXX XXXX 1098"
        assert mask_national_id("123") == "XXXX XXXX XXXX"
        assert mask_national_id("") == ""
        assert mask_national_id(None) == ""

    def test_normalize_national_id_clean(self):
        norm, err = normalize_national_id("9876 5432 1098")
        assert norm == "987654321098"
        assert err is None

        norm_dash, err = normalize_national_id("9876-5432-1098")
        assert norm_dash == "987654321098"
        assert err is None

    def test_normalize_national_id_ambiguous_characters(self):
        # When letters are present where digits are expected, do NOT silently guess!
        norm, err = normalize_national_id("1234 56B8 9012")
        assert norm is None
        assert err == "AMBIGUOUS_IDENTIFIER"

        norm_o, err = normalize_national_id("1234 560O 9012")
        assert norm_o is None
        assert err == "AMBIGUOUS_IDENTIFIER"

    def test_normalize_invalid_lengths_and_prefixes(self):
        norm, err = normalize_national_id("12345")
        assert err == "INVALID_LENGTH"

        norm_first, err = normalize_national_id("012345678901")
        assert err == "INVALID_FIRST_DIGIT"

        norm_one, err = normalize_national_id("112345678901")
        assert err == "INVALID_FIRST_DIGIT"
