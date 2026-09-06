"""
backend/tests/test_national_id_qr.py

Tests for National ID QR/Barcode validation:
- Detection, decoding, and parsing (XML, JSON, delimited)
- Crucial distinction: PAYLOAD_DECODED != AUTHENTICATED
- OCR <-> QR field consistency comparison
- Malformed payload handling
"""
import pytest
from app.services.documents.national_id.national_id_qr_validator import (
    FieldComparisonResult,
    QRStatus,
    compare_ocr_and_qr,
    parse_national_id_qr_payload,
)


class TestNationalIdQR:
    def test_parse_xml_qr_payload(self):
        xml_payload = (
            '<PrintLetterBarcodeData uid="987654321098" name="RAHUL SHARMA" '
            'dob="15/05/1992" gender="MALE" vtc="New Delhi" dist="New Delhi" '
            'state="Delhi" pc="110001" />'
        )
        parsed = parse_national_id_qr_payload(xml_payload)

        assert parsed["status"] == QRStatus.PAYLOAD_DECODED.value
        # Crucial semantic rule: Decoded does NOT mean cryptographically authenticated!
        assert parsed["is_authenticated"] is False
        assert parsed["identity_number"] == "987654321098"
        assert parsed["masked_identity_number"] == "XXXX XXXX 1098"
        assert parsed["name"] == "RAHUL SHARMA"
        assert parsed["dob"] == "15/05/1992"
        assert parsed["gender"] == "MALE"
        assert "New Delhi" in parsed["address"]

    def test_parse_json_qr_payload(self):
        json_payload = '{"uid": "987654321098", "name": "Rahul Sharma", "dob": "1992-05-15", "gender": "MALE"}'
        parsed = parse_national_id_qr_payload(json_payload)

        assert parsed["status"] == QRStatus.PAYLOAD_DECODED.value
        assert parsed["identity_number"] == "987654321098"
        assert parsed["name"] == "RAHUL SHARMA"

    def test_parse_delimited_qr_payload(self):
        delim_payload = "UID:987654321098|NAME:RAHUL SHARMA|DOB:15/05/1992"
        parsed = parse_national_id_qr_payload(delim_payload)

        assert parsed["status"] == QRStatus.PAYLOAD_DECODED.value
        assert parsed["identity_number"] == "987654321098"
        assert parsed["name"] == "RAHUL SHARMA"

    def test_malformed_payload(self):
        malformed = "NOT_A_VALID_BARCODE_FORMAT_RANDOM_GARBAGE"
        parsed = parse_national_id_qr_payload(malformed)
        assert parsed["status"] == QRStatus.PAYLOAD_MALFORMED.value

    def test_empty_or_none_payload(self):
        parsed = parse_national_id_qr_payload("")
        assert parsed["status"] == QRStatus.NOT_FOUND.value

    def test_compare_ocr_and_qr_matched(self):
        qr_data = {
            "status": QRStatus.PAYLOAD_DECODED.value,
            "identity_number": "987654321098",
            "name": "RAHUL SHARMA",
        }
        ocr_fields = {
            "identity_number": "9876 5432 1098",
            "name": "RAHUL SHARMA",
        }

        res = compare_ocr_and_qr(ocr_fields, qr_data)
        assert res["overall_consistency"] == FieldComparisonResult.MATCHED.value
        assert res["authentication_status"] == "PAYLOAD_DECODED"  # Never AUTHENTICATED
        assert res["field_results"]["identity_number"] == FieldComparisonResult.MATCHED.value
        assert res["field_results"]["name"] == FieldComparisonResult.MATCHED.value

    def test_compare_ocr_and_qr_mismatch(self):
        qr_data = {
            "status": QRStatus.PAYLOAD_DECODED.value,
            "identity_number": "111122223333",
            "name": "DIFFERENT PERSON",
        }
        ocr_fields = {
            "identity_number": "9876 5432 1098",
            "name": "RAHUL SHARMA",
        }

        res = compare_ocr_and_qr(ocr_fields, qr_data)
        assert res["overall_consistency"] == FieldComparisonResult.MISMATCH.value
        assert res["field_results"]["identity_number"] == FieldComparisonResult.MISMATCH.value
