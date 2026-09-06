"""
backend/tests/test_dl_parser.py

Unit tests for Driving License field extraction, normalization, and layout handling.
"""
import pytest
from app.schemas.ocr import OCRRegionRaw
from app.services.documents.driving_license.dl_field_normalizer import (
    extract_state_from_license_number,
    normalize_blood_group,
    normalize_dl_date,
    normalize_license_number,
    normalize_vehicle_classes,
)
from app.services.documents.driving_license.dl_parser import parse_driving_license


class TestDLFieldNormalizer:
    def test_normalize_license_number_clean(self):
        assert normalize_license_number("DL-0420110012345") == "DL0420110012345"
        assert normalize_license_number("TN09 20201234567") == "TN0920201234567"
        assert normalize_license_number("  mh-12/2018/0054321  ") == "MH1220180054321"

    def test_normalize_license_number_empty_or_none(self):
        assert normalize_license_number(None) is None
        assert normalize_license_number("") is None
        assert normalize_license_number("   ") is None

    def test_normalize_dates(self):
        assert normalize_dl_date("1992-05-15") == "1992-05-15"
        assert normalize_dl_date("15/05/1992") == "1992-05-15"
        assert normalize_dl_date("15-05-1992") == "1992-05-15"
        assert normalize_dl_date("15 MAY 1992") == "1992-05-15"
        assert normalize_dl_date("invalid") is None

    def test_normalize_blood_groups(self):
        assert normalize_blood_group("O+ve") == "O+"
        assert normalize_blood_group("B +ve") == "B+"
        assert normalize_blood_group("AB-") == "AB-"
        assert normalize_blood_group("INVALID") is None

    def test_normalize_vehicle_classes(self):
        res = normalize_vehicle_classes("COV: MCWG, LMV, TRANS")
        assert "MCWG" in res
        assert "LMV" in res
        assert "TRANS" in res

    def test_extract_state(self):
        assert extract_state_from_license_number("DL0420110012345") == "Delhi"
        assert extract_state_from_license_number("TN0920201234567") == "Tamil Nadu"
        assert extract_state_from_license_number("MH1220180054321") == "Maharashtra"
        assert extract_state_from_license_number("KA0120190001234") == "Karnataka"


class TestDLParser:
    def test_parse_valid_indian_dl(self):
        regions = [
            OCRRegionRaw(text="UNION OF INDIA", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 40], [200, 40], [200, 60], [10, 60]]),
            OCRRegionRaw(text="DL NO: DL0420110012345", confidence=0.97, bbox=[[10, 70], [250, 70], [250, 90], [10, 90]]),
            OCRRegionRaw(text="HOLDER NAME: RAHUL SHARMA", confidence=0.96, bbox=[[10, 100], [250, 100], [250, 120], [10, 120]]),
            OCRRegionRaw(text="DOB: 15/05/1992", confidence=0.95, bbox=[[10, 130], [200, 130], [200, 150], [10, 150]]),
            OCRRegionRaw(text="ISSUE DATE: 15/05/2011", confidence=0.94, bbox=[[10, 160], [200, 160], [200, 180], [10, 180]]),
            OCRRegionRaw(text="VALID TILL: 14/05/2035", confidence=0.94, bbox=[[10, 190], [200, 190], [200, 210], [10, 210]]),
            OCRRegionRaw(text="BLOOD GROUP: O+", confidence=0.92, bbox=[[10, 220], [150, 220], [150, 240], [10, 240]]),
            OCRRegionRaw(text="COV: LMV, MCWG", confidence=0.93, bbox=[[10, 250], [180, 250], [180, 270], [10, 270]]),
            OCRRegionRaw(text="ISSUING AUTHORITY: RTO DELHI", confidence=0.91, bbox=[[10, 280], [250, 280], [250, 300], [10, 300]]),
        ]

        res = parse_driving_license(regions)
        assert res.unsupported_layout is False
        assert res.license_number.value == "DL0420110012345"
        assert res.name.value == "RAHUL SHARMA"
        assert res.dob.value == "1992-05-15"
        assert res.issuedDate.value == "2011-05-15"
        assert res.expiry.value == "2035-05-14"
        assert res.blood_group.value == "O+"
        assert "LMV" in res.vehicle_classes.value
        assert "MCWG" in res.vehicle_classes.value
        assert res.state.value == "Delhi"

    def test_parse_missing_optional_fields(self):
        regions = [
            OCRRegionRaw(text="DRIVING LICENCE", confidence=0.98, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegionRaw(text="DL NO: KA0120190001234", confidence=0.97, bbox=[[10, 40], [250, 40], [250, 60], [10, 60]]),
            OCRRegionRaw(text="NAME: PRIYA VERMA", confidence=0.96, bbox=[[10, 70], [250, 70], [250, 90], [10, 90]]),
            OCRRegionRaw(text="DOB: 10/10/1990", confidence=0.95, bbox=[[10, 100], [200, 100], [200, 120], [10, 120]]),
        ]

        res = parse_driving_license(regions)
        assert res.license_number.value == "KA0120190001234"
        assert res.name.value == "PRIYA VERMA"
        assert res.dob.value == "1990-10-10"
        assert res.blood_group.value is None
        assert res.vehicle_classes.value is None

    def test_unsupported_layout(self):
        regions = [
            OCRRegionRaw(text="GROCERY STORE RECEIPT", confidence=0.90, bbox=[[10, 10], [100, 10], [100, 20], [10, 20]]),
            OCRRegionRaw(text="TOTAL AMOUNT: $45.20", confidence=0.92, bbox=[[10, 30], [120, 30], [120, 40], [10, 40]]),
        ]
        res = parse_driving_license(regions)
        assert res.unsupported_layout is True
        assert res.license_number.value is None
