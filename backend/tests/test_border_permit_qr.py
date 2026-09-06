"""
backend/tests/test_border_permit_qr.py

Unit tests for Border Permit QR code decoding and field consistency verification.
Verifies JSON, XML, delimited parsing, and unauthenticated state labels.
"""
from app.schemas.cross_document import RelationshipStatus
from app.services.documents.border_permit.border_permit_qr_validator import (
    compare_ocr_and_border_permit_qr,
    parse_border_permit_qr_payload,
)


class TestBorderPermitQR:
    def test_parse_json_qr_payload(self):
        payload = '{"permit_number": "BP-2026-000123", "name": "ALEX DUPONT", "passport_number": "P1234567", "valid_to": "2026-12-31"}'
        parsed = parse_border_permit_qr_payload(payload)

        assert parsed["decoded"] is True
        assert parsed["status"] == "PAYLOAD_DECODED"
        assert parsed["authentication"] == "NOT VERIFIED"
        assert parsed["fields"]["permit_number"] == "BP2026000123"
        assert parsed["fields"]["name"] == "ALEX DUPONT"
        assert parsed["fields"]["passport_number"] == "P1234567"
        assert parsed["fields"]["valid_to"] == "2026-12-31"

    def test_parse_xml_qr_payload(self):
        payload = '<BorderPermit permitNo="BP2026000123" name="ALEX DUPONT" passportNo="P1234567" validTo="2026-12-31" />'
        parsed = parse_border_permit_qr_payload(payload)

        assert parsed["decoded"] is True
        assert parsed["status"] == "PAYLOAD_DECODED"
        assert parsed["authentication"] == "NOT VERIFIED"
        assert parsed["fields"]["permit_number"] == "BP2026000123"
        assert parsed["fields"]["name"] == "ALEX DUPONT"
        assert parsed["fields"]["passport_number"] == "P1234567"

    def test_parse_delimited_qr_payload(self):
        payload = "BP=BP-2026-000123|NAME=ALEX DUPONT|PPT=P1234567|TO=2026-12-31"
        parsed = parse_border_permit_qr_payload(payload)

        assert parsed["decoded"] is True
        assert parsed["status"] == "PAYLOAD_DECODED"
        assert parsed["authentication"] == "NOT VERIFIED"
        assert parsed["fields"]["permit_number"] == "BP2026000123"
        assert parsed["fields"]["name"] == "ALEX DUPONT"

    def test_malformed_payload(self):
        payload = "NOT A VALID FORMAT AT ALL $$$"
        parsed = parse_border_permit_qr_payload(payload)
        assert parsed["decoded"] is False
        assert parsed["status"] == "MALFORMED_PAYLOAD"
        assert parsed["authentication"] == "NOT VERIFIED"

    def test_compare_ocr_and_qr_matched(self):
        ocr_data = {
            "permitNumber": "BP2026000123",
            "name": "ALEX DUPONT",
            "passportNumber": "P1234567",
        }
        qr_payload = '{"permit_number": "BP2026000123", "name": "ALEX DUPONT", "passport_number": "P1234567"}'

        comp = compare_ocr_and_border_permit_qr(ocr_data, qr_payload)
        assert comp["status"] == RelationshipStatus.MATCHED.value
        assert comp["authentication"] == "NOT VERIFIED"
        assert comp["field_matches"]["permit_number"] == RelationshipStatus.MATCHED.value
        assert comp["field_matches"]["passport_number"] == RelationshipStatus.MATCHED.value
        assert len(comp["inconsistencies"]) == 0

    def test_compare_ocr_and_qr_mismatch(self):
        ocr_data = {
            "permitNumber": "BP2026000123",
            "name": "ALEX DUPONT",
            "passportNumber": "P1234567",
        }
        # QR contains a different passport number
        qr_payload = '{"permit_number": "BP2026000123", "name": "ALEX DUPONT", "passport_number": "P9999999"}'

        comp = compare_ocr_and_border_permit_qr(ocr_data, qr_payload)
        assert comp["status"] == RelationshipStatus.MISMATCH.value
        assert len(comp["inconsistencies"]) > 0
        assert any("Passport reference mismatch" in inc for inc in comp["inconsistencies"])
