"""
tests/test_visa_validator.py

Tests for Visa structural validation (required fields, expiration,
date chronology, format validation, and lack of ICAO MRZ assumptions).
"""
import datetime
import pytest
from app.schemas.ocr import TravelerFields
from app.services.documents.visa.visa_validator import validate_visa_document


class TestVisaValidator:
    def test_valid_visa_passes_all_checks(self):
        traveler = TravelerFields(
            name="ELIZABETH SWAN",
            docNumber="E99887766",
            dob="1992-04-18",
            nationality="GBR",
            issuedDate="2022-06-01",
            expiry="2032-06-01",
            passportNumber="P12345678",
            visaType="TOURIST",
            entries="MULTIPLE",
            authority="CONSULATE GENERAL",
        )
        ref_date = datetime.date(2023, 1, 1)
        result = validate_visa_document(traveler, reference_date=ref_date)
        assert result["status"] == "passed"
        assert len(result["issues"]) == 0
        assert result["checks"]["required_fields"]["valid"] is True
        assert result["checks"]["visa_number_format"]["valid"] is True
        assert result["checks"]["date_chronology"]["valid"] is True
        assert result["checks"]["expiry_date"]["valid"] is True
        assert result["checks"]["expiry_date"]["expired"] is False

    def test_expired_visa_fails_expiration_check(self):
        traveler = TravelerFields(
            name="JAMES NORRINGTON",
            docNumber="V11223344",
            dob="1980-01-01",
            issuedDate="2015-01-01",
            expiry="2020-01-01",
            passportNumber="P9876543",
        )
        ref_date = datetime.date(2023, 1, 1)
        result = validate_visa_document(traveler, reference_date=ref_date)
        assert result["status"] == "failed"
        assert result["checks"]["expiry_date"]["expired"] is True
        assert any(i["check"] == "expiry_date" and i["severity"] == "critical" for i in result["issues"])

    def test_inverted_dates_fail_chronology(self):
        """Issue date after expiry date is impossible and must fail."""
        traveler = TravelerFields(
            name="WILL TURNER",
            docNumber="V99001122",
            dob="1990-01-01",
            issuedDate="2025-01-01",
            expiry="2023-01-01",
        )
        result = validate_visa_document(traveler)
        assert result["status"] == "failed"
        assert result["checks"]["date_chronology"]["valid"] is False
        assert any(i["check"] == "date_chronology" for i in result["issues"])

    def test_dob_after_issue_date_fails(self):
        """Date of birth on or after issue date is an impossible chronology."""
        traveler = TravelerFields(
            name="BABY TRAVELER",
            docNumber="V55443322",
            dob="2024-05-01",
            issuedDate="2020-01-01",
            expiry="2030-01-01",
        )
        result = validate_visa_document(traveler)
        assert result["status"] == "failed"
        assert result["checks"]["date_chronology"]["valid"] is False

    def test_missing_required_fields_produces_critical_issue(self):
        """Missing visa number and name."""
        traveler = TravelerFields(
            name=None,
            docNumber=None,
            expiry="2028-12-31",
        )
        result = validate_visa_document(traveler)
        assert result["status"] == "failed"
        assert result["checks"]["required_fields"]["valid"] is False
        assert any(i["check"] == "required_fields" for i in result["issues"])

    def test_no_traveler_data_returns_insufficient_data(self):
        result = validate_visa_document(None)
        assert result["status"] == "insufficient_data"
        assert result["checks"]["required_fields"]["status"] == "insufficient_data"

    def test_no_icao_checksum_checks_present(self):
        """CRITICAL: Visa validation must NOT invent or copy Passport ICAO TD3 checksum rules."""
        traveler = TravelerFields(
            name="TEST TRAVELER",
            docNumber="V1234567",
            expiry="2028-01-01",
        )
        result = validate_visa_document(traveler)
        assert "composite_checksum" not in result["checks"]
        assert "doc_number_checksum" not in result["checks"]
        assert "dob_checksum" not in result["checks"]
        assert "expiry_checksum" not in result["checks"]
