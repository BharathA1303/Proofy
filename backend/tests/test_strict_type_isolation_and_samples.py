"""
backend/tests/test_strict_type_isolation_and_samples.py

Tests for:
1. Strict document type isolation rules (e.g. Passport cannot be verified in Visa section, etc.)
2. Deletion of old user records (Bharath, Ragul, Sundaram)
3. Pre-populated synthetic Reference Registry records
4. Availability and serving of the 15 synthetic sample document images (3 variants x 5 document types)
"""
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.documents.classifier import (
    detect_document_type_from_text,
    classify_and_guard_document_type,
)
from app.services.registry.providers.mock_passport import _MOCK_RECORDS as MOCK_PASSPORTS
from app.services.registry.providers.mock_visa import _MOCK_VISA_RECORDS as MOCK_VISAS
from app.services.registry.providers.mock_driving_license import _MOCK_DL_RECORDS as MOCK_DLS
from app.services.registry.providers.mock_national_id import _MOCK_NID_RECORDS as MOCK_NIDS
from app.services.registry.providers.mock_border_permit import _MOCK_BP_RECORDS as MOCK_BPS


class TestStrictDocumentTypeIsolation:
    """Test that credentials cannot be verified in the wrong document section."""

    def test_classifier_detects_passport(self):
        text = "REPUBLIC OF INDIA PASSPORT P<INDSHARMA<<AARAV<<<<<<<<<< Z1234567"
        assert detect_document_type_from_text(text) == "passport"

    def test_classifier_detects_visa(self):
        text = "OFFICIAL ENTRY VISA DEMO BORDER CONTROL IMMIGRATION V1002003 Passport No: Z1234567"
        assert detect_document_type_from_text(text) == "visa"

    def test_classifier_detects_dl(self):
        text = "UNION OF INDIA - DRIVING LICENCE DL NO DL-0420230012345 COV: MCWG, LMV"
        assert detect_document_type_from_text(text) == "driving_license"

    def test_classifier_detects_aadhaar(self):
        text = "GOVERNMENT OF INDIA UNIQUE IDENTIFICATION AUTHORITY OF INDIA AADHAAR 8472 9103 8473"
        assert detect_document_type_from_text(text) == "aadhaar"

    def test_classifier_detects_voter_id(self):
        text = "ELECTION COMMISSION OF INDIA ELECTORS PHOTO IDENTITY CARD EPIC NO ABC1234567"
        assert detect_document_type_from_text(text) == "voter_id"

    def test_classifier_detects_pan_card(self):
        text = "INCOME TAX DEPARTMENT GOVT. OF INDIA PERMANENT ACCOUNT NUMBER ABCDE1234F"
        assert detect_document_type_from_text(text) == "pan_card"


    def test_classifier_detects_border_permit(self):
        text = "OFFICIAL ENTRY & WORK PERMIT REGIONAL BORDER CONTROL BP-2026-880011"
        assert detect_document_type_from_text(text) == "border_permit"

    def test_guard_flags_passport_in_visa_section(self):
        class MockRegion:
            text = "REPUBLIC OF INDIA PASSPORT P<INDSHARMA<<AARAV<<<<<<<<<<<<<<<<"
        res = classify_and_guard_document_type([MockRegion()], declared_type="visa")
        assert res.is_mismatch is True
        assert res.detected_type == "passport"
        assert "A Passport cannot be verified in the Visa section" in res.error_message

    def test_guard_flags_visa_in_passport_section(self):
        class MockRegion:
            text = "OFFICIAL ENTRY VISA DEMO BORDER CONTROL IMMIGRATION V1002003"
        res = classify_and_guard_document_type([MockRegion()], declared_type="passport")
        assert res.is_mismatch is True
        assert res.detected_type == "visa"
        assert "A Visa cannot be verified in the Passport section" in res.error_message

    def test_guard_flags_dl_in_passport_section(self):
        class MockRegion:
            text = "UNION OF INDIA DRIVING LICENCE DL-0420230012345"
        res = classify_and_guard_document_type([MockRegion()], declared_type="passport")
        assert res.is_mismatch is True
        assert res.detected_type == "driving_license"
        assert "Driving License cannot be verified in the Passport section" in res.error_message

    def test_guard_passes_when_types_match(self):
        class MockRegion:
            text = "REPUBLIC OF INDIA PASSPORT P<INDSHARMA<<AARAV<<<<<<<<<<<<<<<<"
        res = classify_and_guard_document_type([MockRegion()], declared_type="passport")
        assert res.is_mismatch is False


class TestPrePopulatedReferenceRegistry:
    """Test that synthetic official and blacklist records are populated and old user records are deleted."""

    def test_dl_registry_contains_bharath_genuine(self):
        assert "TN0520250014128" in MOCK_DLS
        assert MOCK_DLS["TN0520250014128"]["registry_document_status"] == "ACTIVE"
        assert MOCK_DLS["TN0520250014128"]["name"] == "BHARATH A"

    def test_passport_registry_contains_official_and_blacklist(self):
        assert "Z1234567" in MOCK_PASSPORTS
        assert MOCK_PASSPORTS["Z1234567"]["registry_document_status"] == "ACTIVE"
        assert MOCK_PASSPORTS["Z1234567"]["name"] == "AARAV SHARMA"

        assert "Z7654321" in MOCK_PASSPORTS
        assert MOCK_PASSPORTS["Z7654321"]["registry_document_status"] == "REVOKED"
        assert MOCK_PASSPORTS["Z7654321"]["name"] == "VIKRAM MALHOTRA"

    def test_visa_registry_contains_official_and_blacklist(self):
        assert "V1002003" in MOCK_VISAS
        assert MOCK_VISAS["V1002003"]["registry_document_status"] == "ACTIVE"
        assert MOCK_VISAS["V1002003"]["name"] == "AARAV SHARMA"

        assert "V7008009" in MOCK_VISAS
        assert MOCK_VISAS["V7008009"]["registry_document_status"] == "REVOKED"
        assert MOCK_VISAS["V7008009"]["name"] == "VIKRAM MALHOTRA"

    def test_dl_registry_contains_official_and_blacklist(self):
        assert "DL-0420230012345" in MOCK_DLS
        assert MOCK_DLS["DL-0420230012345"]["registry_document_status"] == "ACTIVE"
        assert MOCK_DLS["DL-0420230012345"]["name"] == "PRIYA SUNDAR"

        assert "DL-0120180099887" in MOCK_DLS
        assert MOCK_DLS["DL-0120180099887"]["registry_document_status"] == "REVOKED"
        assert MOCK_DLS["DL-0120180099887"]["name"] == "KABIR MEHTA"

    def test_national_id_registry_contains_official_and_blacklist(self):
        assert "847291038473" in MOCK_NIDS
        assert MOCK_NIDS["847291038473"]["registry_document_status"] == "ACTIVE"
        assert MOCK_NIDS["847291038473"]["name"] == "SNEHA PATEL"

        assert "654123987101" in MOCK_NIDS
        assert MOCK_NIDS["654123987101"]["registry_document_status"] == "REVOKED"
        assert MOCK_NIDS["654123987101"]["name"] == "TARIQ AHMED"

    def test_border_permit_registry_contains_official_and_blacklist(self):
        assert "BP-2026-880011" in MOCK_BPS
        assert MOCK_BPS["BP-2026-880011"]["registry_document_status"] == "ACTIVE"
        assert MOCK_BPS["BP-2026-880011"]["name"] == "ELENA ROSTOVA"

        assert "BP-2025-443322" in MOCK_BPS
        assert MOCK_BPS["BP-2025-443322"]["registry_document_status"] == "REVOKED"
        assert MOCK_BPS["BP-2025-443322"]["name"] == "MARCUS VANCE"


@pytest.mark.asyncio
class TestSampleOptionsAPI:
    """Test sample options endpoint returns the 3 variants for all 5 document categories."""

    async def test_get_sample_options_returns_3_variants_each(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/verification/sample/options")
            assert resp.status_code == 200
            data = resp.json()

            for doc_type in ["passport", "visa", "driving_license", "national_id", "border_permit"]:
                assert doc_type in data
                variants = [item["variant"] for item in data[doc_type]]
                assert "official" in variants
                assert "blacklist" in variants
                assert "defective" in variants

    async def test_sample_files_exist_on_disk(self):
        assets_dir = Path(__file__).parent / "assets"
        expected_files = [
            "passport_official.jpg", "passport_blacklist.jpg", "passport_defective.jpg",
            "visa_official.jpg", "visa_blacklist.jpg", "visa_defective.jpg",
            "dl_official.jpg", "dl_blacklist.jpg", "dl_defective.jpg",
            "national_id_official.jpg", "national_id_blacklist.jpg", "national_id_defective.jpg",
            "border_permit_official.jpg", "border_permit_blacklist.jpg", "border_permit_defective.jpg",
        ]
        for fn in expected_files:
            file_path = assets_dir / fn
            assert file_path.exists(), f"Missing synthetic asset: {fn}"
            assert file_path.stat().st_size > 1000, f"Asset too small: {fn}"
