"""
backend/tests/test_national_id_validator.py

Tests for Module 2 National ID Document Validation:
- Required field presence
- 12-digit format and Verhoeff checksum validation
- Checksum failure produces FORMAT_WARNING (not "forged document")
- Date / Year of birth plausibility
- QR payload field consistency comparison
"""
import datetime
import pytest
from app.schemas.ocr import TravelerFields
from app.services.documents.national_id.national_id_identifier_validator import (
    generate_valid_national_id,
)
from app.services.documents.national_id.national_id_validator import (
    validate_national_id_document,
)


class TestNationalIdValidator:
    def test_valid_national_id(self):
        valid_id = generate_valid_national_id("98765432109")
        traveler = TravelerFields(
            name="RAHUL SHARMA",
            docNumber=valid_id,
            dob="1992-05-15",
            gender="MALE",
        )

        res = validate_national_id_document(traveler, reference_date=datetime.date(2026, 1, 1))

        assert res["status"] == "passed"
        assert res["checks"]["required_fields"]["valid"] is True
        assert res["checks"]["identifier_format"]["valid"] is True
        assert res["checks"]["identifier_checksum"]["checksum_status"] == "PASS"
        assert res["checks"]["date_validity"]["valid"] is True

    def test_missing_required_fields(self):
        traveler = TravelerFields(
            name="",
            docNumber="",
            dob="",
        )

        res = validate_national_id_document(traveler)
        assert res["status"] == "failed"
        assert res["checks"]["required_fields"]["valid"] is False

    def test_checksum_failure_is_warning_not_forgery(self):
        # A corrupted checksum must produce a warning/format issue, NOT an accusation of forgery!
        valid_id = generate_valid_national_id("98765432109")
        corrupted_id = valid_id[:-1] + str((int(valid_id[-1]) + 1) % 10)

        traveler = TravelerFields(
            name="RAHUL SHARMA",
            docNumber=corrupted_id,
            dob="1992-05-15",
        )

        res = validate_national_id_document(traveler)

        assert res["status"] == "warning"
        assert res["checks"]["identifier_checksum"]["checksum_status"] == "FAIL"
        # Confirm it's not claiming forged
        assert "forged" not in res["summary"].lower()
        assert any(iss["check"] == "identifier_checksum" and iss["severity"] == "warning" for iss in res["issues"])

    def test_year_only_dob_validation(self):
        valid_id = generate_valid_national_id("23456789012")
        traveler = TravelerFields(
            name="PRIYA PATEL",
            docNumber=valid_id,
            yearOfBirth="1995",
        )

        res = validate_national_id_document(traveler, reference_date=datetime.date(2026, 1, 1))
        assert res["status"] == "passed"
        assert res["checks"]["date_validity"]["is_year_only"] is True
        assert res["checks"]["date_validity"]["year_of_birth"] == 1995

    def test_future_birth_year_rejected(self):
        valid_id = generate_valid_national_id("23456789012")
        traveler = TravelerFields(
            name="TIME TRAVELER",
            docNumber=valid_id,
            yearOfBirth="2040",
        )

        res = validate_national_id_document(traveler, reference_date=datetime.date(2026, 1, 1))
        assert res["status"] == "failed"
        assert res["checks"]["date_validity"]["valid"] is False

    def test_qr_consistency_matched_and_mismatch(self):
        valid_id = generate_valid_national_id("98765432109")

        # 1. Matching QR payload
        matching_payload = f'<PrintLetterBarcodeData uid="{valid_id}" name="RAHUL SHARMA" dob="15/05/1992" />'
        traveler_matched = TravelerFields(
            name="RAHUL SHARMA",
            docNumber=valid_id,
            dob="1992-05-15",
            qrPayload=matching_payload,
        )
        res_matched = validate_national_id_document(traveler_matched, reference_date=datetime.date(2026, 1, 1))
        assert res_matched["checks"]["qr_consistency"]["status"] == "passed"

        # 2. Mismatched QR payload (different identity number in QR)
        different_id = generate_valid_national_id("33344455566")
        mismatch_payload = f'<PrintLetterBarcodeData uid="{different_id}" name="RAHUL SHARMA" dob="15/05/1992" />'
        traveler_mismatch = TravelerFields(
            name="RAHUL SHARMA",
            docNumber=valid_id,
            dob="1992-05-15",
            qrPayload=mismatch_payload,
        )
        res_mismatch = validate_national_id_document(traveler_mismatch, reference_date=datetime.date(2026, 1, 1))
        assert res_mismatch["checks"]["qr_consistency"]["status"] == "failed"
