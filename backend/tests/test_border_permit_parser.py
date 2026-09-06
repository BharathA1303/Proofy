"""
backend/tests/test_border_permit_parser.py

Unit tests for BorderPermitParser and Border Permit field extraction.
Tests OCR text extraction, field normalization, ambiguity detection,
and unsupported layout rejection.
"""
from app.schemas.ocr import OCRRegionRaw
from app.services.documents.border_permit.border_permit_parser import (
    BorderPermitParser,
    parse_border_permit,
)


class TestBorderPermitParser:
    def test_parse_full_border_permit(self):
        regions = [
            OCRRegionRaw(text="REGIONAL BORDER CONTROL", confidence=0.99, bbox=[[10, 10], [300, 10], [300, 30], [10, 30]]),
            OCRRegionRaw(text="OFFICIAL ENTRY & CROSSING PERMIT", confidence=0.99, bbox=[[10, 35], [400, 35], [400, 55], [10, 55]]),
            OCRRegionRaw(text="PERMIT NO: BP-2026-000123", confidence=0.98, bbox=[[285, 110], [600, 110], [600, 130], [285, 130]]),
            OCRRegionRaw(text="HOLDER NAME: ALEX DUPONT", confidence=0.98, bbox=[[285, 150], [600, 150], [600, 170], [285, 170]]),
            OCRRegionRaw(text="DATE OF BIRTH: 12-08-1990", confidence=0.97, bbox=[[285, 190], [600, 190], [600, 210], [285, 210]]),
            OCRRegionRaw(text="LINKED PASSPORT NO: P1234567", confidence=0.99, bbox=[[285, 230], [600, 230], [600, 250], [285, 250]]),
            OCRRegionRaw(text="PERMIT TYPE: ENTRY", confidence=0.98, bbox=[[285, 270], [600, 270], [600, 290], [285, 290]]),
            OCRRegionRaw(text="PORT OF ENTRY: NORTH GATE TERMINAL", confidence=0.96, bbox=[[285, 310], [600, 310], [600, 330], [285, 330]]),
            OCRRegionRaw(text="VALID FROM: 01-01-2026", confidence=0.98, bbox=[[285, 350], [600, 350], [600, 370], [285, 370]]),
            OCRRegionRaw(text="VALID TO: 31-12-2026", confidence=0.98, bbox=[[285, 390], [600, 390], [600, 410], [285, 410]]),
            OCRRegionRaw(text="ISSUING AUTHORITY: Border Management Authority", confidence=0.97, bbox=[[285, 430], [600, 430], [600, 450], [285, 450]]),
        ]

        parsed = parse_border_permit(regions)

        assert parsed.permit_number.value == "BP2026000123"
        assert parsed.docNumber.value == "BP2026000123"
        assert parsed.name.value == "ALEX DUPONT"
        assert parsed.dob.value == "1990-08-12"
        assert parsed.passport_number.value == "P1234567"
        assert parsed.permit_type.value == "ENTRY"
        assert parsed.port_of_entry.value == "NORTH GATE TERMINAL"
        assert parsed.valid_from.value == "2026-01-01"
        assert parsed.valid_to.value == "2026-12-31"
        assert parsed.expiry.value == "2026-12-31"
        assert parsed.issuing_authority.value == "Border Management Authority"
        assert parsed.is_ambiguous_identifier is False
        assert parsed.unsupported_layout is False

    def test_ambiguous_identifier_detection(self):
        regions = [
            OCRRegionRaw(text="BORDER PERMIT", confidence=0.99, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            # Notice letter 'O' instead of digit '0' in the numeric tail
            OCRRegionRaw(text="PERMIT NO: BP-2026-00O123", confidence=0.95, bbox=[[10, 40], [300, 40], [300, 60], [10, 60]]),
            OCRRegionRaw(text="HOLDER: JOHN SMITH", confidence=0.98, bbox=[[10, 70], [300, 70], [300, 90], [10, 90]]),
            OCRRegionRaw(text="VALID TO: 2026-12-31", confidence=0.98, bbox=[[10, 100], [300, 100], [300, 120], [10, 120]]),
        ]

        parsed = parse_border_permit(regions)
        assert parsed.is_ambiguous_identifier is True
        assert parsed.name.value == "JOHN SMITH"

    def test_unsupported_layout_rejection(self):
        # Image text that doesn't look like a Border Permit
        regions = [
            OCRRegionRaw(text="GROCERY STORE RECEIPT", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="Total Amount: $45.50", confidence=0.98, bbox=[[10, 40], [200, 40], [200, 60], [10, 60]]),
            OCRRegionRaw(text="Thank you for shopping!", confidence=0.98, bbox=[[10, 70], [200, 70], [200, 90], [10, 90]]),
        ]

        parsed = parse_border_permit(regions)
        assert parsed.unsupported_layout is True
        assert len(parsed.unsupported_reasons) > 0
        assert parsed.permit_number.value is None

    def test_header_noise_filtered_from_name(self):
        regions = [
            OCRRegionRaw(text="BORDER CROSSING PERMIT", confidence=0.99, bbox=[[10, 10], [300, 10], [300, 30], [10, 30]]),
            OCRRegionRaw(text="BP-2026-000123", confidence=0.99, bbox=[[10, 40], [300, 40], [300, 60], [10, 60]]),
            OCRRegionRaw(text="HOLDER NAME: MARIA GARCIA", confidence=0.98, bbox=[[10, 70], [300, 70], [300, 90], [10, 90]]),
        ]
        parsed = parse_border_permit(regions)
        assert parsed.name.value == "MARIA GARCIA"
        assert "BORDER" not in parsed.name.value
