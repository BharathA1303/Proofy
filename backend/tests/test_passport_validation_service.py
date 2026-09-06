"""
backend/tests/test_passport_validation_service.py

End-to-end unit tests for Module 2 Passport Validation Service.
Tests valid vectors, the Passport Binding Trap, checksum tamperings,
expiration, and logging safety.
"""
import datetime
import logging
import pytest

from app.schemas.ocr import MRZData, TravelerFields
from app.services.validation.passport_validation_service import validate_passport_document


class TestPassportValidationService:
    """Comprehensive test suite for validate_passport_document."""

    # 100% mathematically valid ICAO Doc 9303 TD3 test vector
    LINE1_VALID = "P<INDMALHOTRA<<ASHOK<KUMAR<<<<<<<<<<<<<<<<<<"  # 44 chars
    LINE2_VALID = "A1234567<6IND9001011M2912316<<<<<<<<<<<<<<<8"  # 44 chars

    @pytest.fixture
    def valid_traveler(self):
        return TravelerFields(
            docNumber="A1234567",
            name="ASHOK KUMAR MALHOTRA",
            nationality="IND",
            dob="01/01/1990",
            gender="M",
            expiry="31/12/2029",
        )

    @pytest.fixture
    def valid_mrz(self):
        return MRZData(
            line1=self.LINE1_VALID,
            line2=self.LINE2_VALID,
            raw_line1=self.LINE1_VALID,
            raw_line2=self.LINE2_VALID,
        )

    @pytest.fixture
    def reference_date(self):
        # 1 January 2026
        return datetime.date(2026, 1, 1)

    def test_fully_valid_passport_passes(self, valid_mrz, valid_traveler, reference_date):
        res = validate_passport_document(valid_mrz, valid_traveler, reference_date=reference_date)

        assert res.status == "passed"
        assert "passed successfully" in res.summary
        assert res.checks.mrz_structure.status == "passed"
        assert res.checks.document_number_checksum.valid is True
        assert res.checks.document_number_checksum.status == "passed"
        assert res.checks.dob_checksum.valid is True
        assert res.checks.dob_checksum.status == "passed"
        assert res.checks.expiry_checksum.valid is True
        assert res.checks.expiry_checksum.status == "passed"
        assert res.checks.composite_checksum.valid is True
        assert res.checks.composite_checksum.status == "passed"
        assert res.checks.expiry_date.expired is False
        assert res.checks.passport_number_binding.valid is True
        assert res.checks.passport_number_binding.match is True
        assert res.checks.passport_number_binding.status == "passed"
        assert len(res.issues) == 0

    def test_passport_binding_trap_mismatch_fails(self, valid_mrz, valid_traveler, reference_date):
        """
        The Passport Binding Trap:
        The MRZ says A1234567, but the visual document number was altered to X9999999.
        Even if the MRZ checksum is valid, validation MUST FAIL.
        """
        tampered_traveler = valid_traveler.model_copy(update={"docNumber": "X9999999"})
        res = validate_passport_document(valid_mrz, tampered_traveler, reference_date=reference_date)

        assert res.status == "failed"
        assert res.checks.passport_number_binding.match is False
        assert res.checks.passport_number_binding.status == "failed"
        critical_issues = [iss for iss in res.issues if iss.severity == "critical"]
        assert len(critical_issues) > 0
        assert any("Binding mismatch" in iss.message for iss in critical_issues)

    def test_composite_checksum_failure_causes_critical_failure(self, valid_traveler, reference_date):
        """Altering a digit without fixing the composite check digit fails validation."""
        # Change composite check digit at index 43 from '8' to '9'
        tampered_l2 = "A1234567<6IND9001011M2912316<<<<<<<<<<<<<<<9"
        mrz = MRZData(line1=self.LINE1_VALID, line2=tampered_l2)

        res = validate_passport_document(mrz, valid_traveler, reference_date=reference_date)
        assert res.status == "failed"
        assert res.checks.composite_checksum.valid is False
        assert res.checks.composite_checksum.status == "failed"
        assert any("Composite check digit mismatch" in iss.message for iss in res.issues)

    def test_doc_number_checksum_failure(self, valid_traveler, reference_date):
        """Altering doc number check digit at index 9 from '6' to '0'."""
        tampered_l2 = "A1234567<0IND9001011M2912316<<<<<<<<<<<<<<<8"
        mrz = MRZData(line1=self.LINE1_VALID, line2=tampered_l2)

        res = validate_passport_document(mrz, valid_traveler, reference_date=reference_date)
        assert res.status == "failed"
        assert res.checks.document_number_checksum.valid is False

    def test_expired_passport_causes_failure(self, valid_traveler):
        """Passport with expiry in 2020 evaluated against 2026."""
        # Expiry 201231 -> 31 Dec 2020.
        # Check digit for 201231: 2*7 + 0*3 + 1*1 + 2*7 + 3*3 + 1*1 = 14 + 1 + 14 + 9 + 1 = 39 -> 9
        expired_l2 = "A1234567<6IND9001011M2012319<<<<<<<<<<<<<<<2"
        mrz = MRZData(line1=self.LINE1_VALID, line2=expired_l2)
        ref_date = datetime.date(2026, 1, 1)

        res = validate_passport_document(mrz, valid_traveler, reference_date=ref_date)
        assert res.status == "failed"
        assert res.checks.expiry_date.expired is True
        assert res.checks.expiry_date.status == "failed"
        assert any("expired" in iss.message.lower() for iss in res.issues)

    def test_empty_mrz_yields_insufficient_data(self, valid_traveler):
        """When no MRZ data is supplied, returns insufficient_data without crashing."""
        res = validate_passport_document(None, valid_traveler)
        assert res.status == "insufficient_data"
        assert res.checks.mrz_structure.status == "insufficient_data"
        assert res.checks.document_number_checksum.status == "unknown"

    def test_name_mismatch_raises_warning(self, valid_mrz, valid_traveler, reference_date):
        """When VIZ name does not match MRZ name, it records a warning issue."""
        different_traveler = valid_traveler.model_copy(update={"name": "JANE DOE"})
        res = validate_passport_document(valid_mrz, different_traveler, reference_date=reference_date)

        # Still valid MRZ, but consistency check triggers warning
        assert res.status == "warning"
        assert any("Holder name mismatch" in iss.message for iss in res.issues)

    def test_no_pii_in_logs(self, valid_mrz, valid_traveler, reference_date, caplog):
        """Verify logging adheres to security rule: no passport numbers or traveler names."""
        with caplog.at_level(logging.INFO):
            validate_passport_document(valid_mrz, valid_traveler, reference_date=reference_date)

        log_text = caplog.text
        assert "A1234567" not in log_text
        assert "MALHOTRA" not in log_text
        assert "ASHOK" not in log_text
        assert "Passport validation completed" in log_text
