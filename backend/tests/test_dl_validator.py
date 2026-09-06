"""
backend/tests/test_dl_validator.py

Unit tests for Driving License structural validation service.
"""
import datetime
import pytest
from app.schemas.ocr import TravelerFields
from app.services.documents.driving_license.dl_validator import validate_driving_license_document


class TestDLValidator:
    def test_valid_dl_passes_all_checks(self):
        traveler = TravelerFields(
            name="RAHUL SHARMA",
            docNumber="DL0420110012345",
            dob="1992-05-15",
            issuedDate="2011-05-15",
            expiry="2035-05-14",
        )
        res = validate_driving_license_document(
            traveler=traveler,
            reference_date=datetime.date(2025, 1, 1),
        )
        assert res["status"] == "passed"
        assert res["checks"]["required_fields"]["valid"] is True
        assert res["checks"]["license_number_format"]["valid"] is True
        assert res["checks"]["date_chronology"]["valid"] is True
        assert res["checks"]["age_eligibility"]["valid"] is True
        assert res["checks"]["expiry_date"]["valid"] is True
        assert res["checks"]["expiry_date"]["expired"] is False

    def test_expired_dl_fails_expiry_check(self):
        traveler = TravelerFields(
            name="RAHUL SHARMA",
            docNumber="DL0420110012345",
            dob="1980-01-01",
            issuedDate="2000-01-01",
            expiry="2020-01-01",
        )
        res = validate_driving_license_document(
            traveler=traveler,
            reference_date=datetime.date(2025, 1, 1),
        )
        assert res["status"] == "failed"
        assert res["checks"]["expiry_date"]["expired"] is True
        assert res["checks"]["expiry_date"]["valid"] is False
        assert any(i["check"] == "expiry_date" for i in res["issues"])

    def test_inverted_validity_dates_fail_chronology(self):
        traveler = TravelerFields(
            name="RAHUL SHARMA",
            docNumber="DL0420110012345",
            dob="1990-01-01",
            issuedDate="2030-01-01",
            expiry="2025-01-01",
        )
        res = validate_driving_license_document(
            traveler=traveler,
            reference_date=datetime.date(2025, 1, 1),
        )
        assert res["status"] == "failed"
        assert res["checks"]["date_chronology"]["valid"] is False
        assert any(i["check"] == "date_chronology" for i in res["issues"])

    def test_underage_driver_fails_age_eligibility(self):
        # Born in 2000, license supposedly issued in 2010 (age 10)
        traveler = TravelerFields(
            name="MINOR DRIVER",
            docNumber="DL0420110012345",
            dob="2000-01-01",
            issuedDate="2010-01-01",
            expiry="2030-01-01",
        )
        res = validate_driving_license_document(
            traveler=traveler,
            reference_date=datetime.date(2025, 1, 1),
        )
        assert res["status"] == "failed"
        assert res["checks"]["age_eligibility"]["valid"] is False
        assert any(i["check"] == "age_eligibility" for i in res["issues"])

    def test_missing_required_fields_generates_critical_issue(self):
        traveler = TravelerFields(
            name="",
            docNumber="",
            dob="1995-01-01",
        )
        res = validate_driving_license_document(traveler=traveler)
        assert res["status"] == "failed"
        assert res["checks"]["required_fields"]["valid"] is False

    def test_irregular_identifier_format_generates_warning_not_forged(self):
        traveler = TravelerFields(
            name="TEST USER",
            docNumber="INVALID#123",
            dob="1990-01-01",
            issuedDate="2015-01-01",
            expiry="2035-01-01",
        )
        res = validate_driving_license_document(traveler=traveler)
        assert res["checks"]["license_number_format"]["status"] == "warning"
        # Must be warning, not a fraud declaration
        assert "does not confidently match" in res["checks"]["license_number_format"]["message"]

    def test_empty_traveler_data_returns_insufficient_data(self):
        res = validate_driving_license_document(traveler=None)
        assert res["status"] == "insufficient_data"
