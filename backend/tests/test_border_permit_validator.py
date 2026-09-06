"""
backend/tests/test_border_permit_validator.py

Unit tests for Module 2: Border Permit Document Validation.
Tests required fields, permit format, validity chronology, expiration,
and passport reference binding checks.
"""
import datetime
import pytest
from app.schemas.ocr import TravelerFields
from app.services.documents.border_permit.border_permit_validator import (
    validate_border_permit_document,
)


class TestBorderPermitValidator:
    def test_valid_border_permit(self):
        traveler = TravelerFields(
            name="ALEX DUPONT",
            docNumber="BP2026000123",
            permitNumber="BP2026000123",
            dob="1990-08-12",
            passportNumber="P1234567",
            validFrom="2026-01-01",
            validTo="2026-12-31",
            permitType="ENTRY",
            portOfEntry="NORTH GATE",
            authority="Border Management Authority",
        )
        ref_date = datetime.date(2026, 6, 1)
        res = validate_border_permit_document(traveler, reference_date=ref_date)

        assert res["status"] == "passed"
        assert res["checks"]["required_fields"]["valid"] is True
        assert res["checks"]["identifier_format"]["valid"] is True
        assert res["checks"]["validity_period"]["temporal_status"] == "ACTIVE"
        assert res["checks"]["passport_binding"]["valid"] is True
        assert len(res["issues"]) == 0

    def test_missing_required_fields(self):
        traveler = TravelerFields(
            name=None,
            permitNumber=None,
            validTo="2026-12-31",
        )
        res = validate_border_permit_document(traveler)
        assert res["status"] == "failed"
        assert res["checks"]["required_fields"]["valid"] is False
        assert "name" in res["checks"]["required_fields"]["missing"]
        assert "permitNumber" in res["checks"]["required_fields"]["missing"]
        assert any(i["issue_type"] == "REQUIRED_FIELDS_MISSING" for i in res["issues"])

    def test_inverted_validity_dates(self):
        traveler = TravelerFields(
            name="ALEX DUPONT",
            permitNumber="BP2026000123",
            validFrom="2026-12-31",
            validTo="2026-01-01",  # Inverted!
        )
        res = validate_border_permit_document(traveler)
        assert res["status"] == "failed"
        assert res["checks"]["validity_period"]["valid"] is False
        assert res["checks"]["validity_period"]["temporal_status"] == "INVALID_RANGE"
        assert any(i["issue_type"] == "INVALID_DATE_RANGE" for i in res["issues"])

    def test_expired_border_permit_is_warning_not_forgery(self):
        traveler = TravelerFields(
            name="ALEX DUPONT",
            permitNumber="BP2026000123",
            validFrom="2020-01-01",
            validTo="2020-12-31",  # Expired
        )
        ref_date = datetime.date(2026, 6, 1)
        res = validate_border_permit_document(traveler, reference_date=ref_date)

        # Expired is a temporal warning condition, NOT automatic proof of forgery
        assert res["status"] == "warning"
        assert res["checks"]["validity_period"]["temporal_status"] == "EXPIRED"
        assert any(i["issue_type"] == "DOCUMENT_EXPIRED" for i in res["issues"])
        assert not any("forged" in i["description"].lower() for i in res["issues"])

    def test_not_yet_valid_permit(self):
        traveler = TravelerFields(
            name="ALEX DUPONT",
            permitNumber="BP2026000123",
            validFrom="2028-01-01",  # Future start
            validTo="2028-12-31",
        )
        ref_date = datetime.date(2026, 6, 1)
        res = validate_border_permit_document(traveler, reference_date=ref_date)

        assert res["status"] == "warning"
        assert res["checks"]["validity_period"]["temporal_status"] == "NOT_YET_VALID"
        assert any(i["issue_type"] == "DOCUMENT_NOT_YET_VALID" for i in res["issues"])

    def test_qr_consistency_matching_and_mismatch(self):
        # Matched QR payload
        traveler_matched = TravelerFields(
            name="ALEX DUPONT",
            permitNumber="BP2026000123",
            passportNumber="P1234567",
            validFrom="2026-01-01",
            validTo="2026-12-31",
            qrPayload='{"permit_number": "BP2026000123", "name": "ALEX DUPONT", "passport_number": "P1234567"}',
        )
        res_m = validate_border_permit_document(traveler_matched, reference_date=datetime.date(2026, 6, 1))
        assert res_m["checks"]["qr_consistency"]["valid"] is True
        assert res_m["checks"]["qr_consistency"]["status"] == "passed"

        # Mismatched QR payload (different permit number)
        traveler_mismatch = TravelerFields(
            name="ALEX DUPONT",
            permitNumber="BP2026000123",
            passportNumber="P1234567",
            validFrom="2026-01-01",
            validTo="2026-12-31",
            qrPayload='{"permit_number": "BP9999999999", "name": "ALEX DUPONT", "passport_number": "P1234567"}',
        )
        res_mis = validate_border_permit_document(traveler_mismatch, reference_date=datetime.date(2026, 6, 1))
        assert res_mis["checks"]["qr_consistency"]["valid"] is False
        assert any(i["issue_type"] == "QR_OCR_MISMATCH" for i in res_mis["issues"])
