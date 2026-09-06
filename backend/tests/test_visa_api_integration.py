"""
tests/test_visa_api_integration.py

End-to-End API Integration Tests for Visa Verification Pipeline:
- Sample Visa retrieval: GET /api/v1/verification/sample/visa
- OCR routing for Visa: POST /api/v1/verification/ocr
- Document validation for Visa: POST /api/v1/verification/validate
- Forensics routing for Visa: POST /api/v1/verification/forensic
- Registry routing for Visa: POST /api/v1/verification/registry
- Risk engine aggregation for Visa: POST /api/v1/verification/risk
- Unsupported document rejection (driving_license) -> 422
- Unknown document rejection (alien_pass) -> 404/422
"""
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from app.main import app
import app.services.ocr.ocr_engine as ocr_engine_module
from app.services.ocr.ocr_engine import OCRRegion
from tests.forensic_test_utils import encode_jpeg, make_textured_image


client = TestClient(app)

SAMPLE_VISA_PATH = Path(__file__).parent / "assets" / "sample_visa.jpg"


@pytest.fixture(autouse=True)
def mock_ocr_engine_init(monkeypatch):
    """Prevent PaddleOCR from loading models during API tests."""
    monkeypatch.setattr(ocr_engine_module, "init_engine", lambda **kw: None)
    monkeypatch.setattr(ocr_engine_module, "_paddle_ocr_instance", MagicMock())


def _make_synthetic_visa_regions() -> list[OCRRegion]:
    def r(text, top_y=100, conf=0.95):
        return OCRRegion(
            text=text, confidence=conf,
            bbox=[[0, top_y], [300, top_y], [300, top_y+20], [0, top_y+20]],
        )
    return [
        r("VISA / EMBASSY OF THE UNITED STATES", top_y=50),
        r("Visa Number: V88776655", top_y=90),
        r("Surname: CONNOR", top_y=130),
        r("Given Names: SARAH", top_y=160),
        r("Passport Number: P9876543", top_y=190),
        r("Nationality: USA", top_y=220),
        r("Date of Birth: 1985-05-12", top_y=250),
        r("Issue Date: 2022-01-01", top_y=280),
        r("Expiration Date: 2033-01-15", top_y=310),
        r("Visa Type: B1/B2", top_y=340),
        r("Entries: M", top_y=370),
    ]


class TestVisaAPIIntegration:
    def test_get_sample_visa(self):
        resp = client.get("/api/v1/verification/sample/visa")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"
        assert len(resp.content) > 1000

    def test_ocr_visa_document(self, monkeypatch):
        monkeypatch.setattr(ocr_engine_module, "run_ocr", lambda img: _make_synthetic_visa_regions())

        if not SAMPLE_VISA_PATH.exists():
            pytest.skip("sample_visa.jpg not generated")

        with open(SAMPLE_VISA_PATH, "rb") as f:
            files = {"file": ("sample_visa.jpg", f, "image/jpeg")}
            data = {"document_type": "visa"}
            resp = client.post("/api/v1/verification/ocr", files=files, data=data)

        assert resp.status_code == 200
        result = resp.json()
        assert result["document_type"] == "visa"
        assert "verification_id" in result
        assert "traveler" in result
        assert result["traveler"]["docNumber"] == "V88776655"
        assert result["traveler"]["passportNumber"] == "P9876543"
        assert result["status"] in ("completed", "partial")

    def test_validate_visa_document_valid(self):
        payload = {
            "verification_id": "test-v-validate-1",
            "document_type": "visa",
            "traveler": {
                "name": "TEST BEARER",
                "docNumber": "V88776655",
                "dob": "1990-01-01",
                "expiry": "2030-01-01",
                "issuedDate": "2020-01-01",
                "passportNumber": "P1234567",
            },
            "related_passport_number": "P1234567",
        }
        resp = client.post("/api/v1/verification/validate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_type"] == "visa"
        val = data["document_validation"]
        assert val["status"] == "passed"
        assert "required_fields" in val["checks"]
        assert "visa_number_format" in val["checks"]
        assert "cross_document_passport" in val["checks"]

    def test_validate_visa_document_expired(self):
        payload = {
            "verification_id": "test-v-validate-expired",
            "document_type": "visa",
            "traveler": {
                "name": "TEST BEARER",
                "docNumber": "V88776655",
                "dob": "1990-01-01",
                "expiry": "2018-01-01",
                "issuedDate": "2010-01-01",
            },
        }
        resp = client.post("/api/v1/verification/validate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        val = data["document_validation"]
        assert val["status"] == "failed"
        assert val["checks"]["expiry_date"]["expired"] is True

    def test_forensics_visa_endpoint(self):
        img = make_textured_image()
        jpeg_bytes = encode_jpeg(img, quality=90)
        files = {"file": ("sample_visa.jpg", jpeg_bytes, "image/jpeg")}
        data = {
            "document_type": "visa",
            "verification_id": "test-forensic-v-1",
        }
        resp = client.post("/api/v1/verification/forensic", files=files, data=data)

        assert resp.status_code == 200
        result = resp.json()
        assert result["document_type"] == "visa"
        assert "forensic_analysis" in result
        assert result["forensic_analysis"]["status"] in ("completed", "warning")

    def test_registry_visa_endpoint(self):
        # 1. Simulate OCR to populate registry session store
        from app.services.registry.session_store import registry_session_store
        session_id = "test-api-visa-reg-1"
        registry_session_store.set(session_id, {
            "document_type": "visa",
            "document_number": "TESTVISA001",
            "name": "SARAH CONNOR",
            "date_of_birth": "1985-05-12",
            "nationality": "USA",
            "passport_number": "P9876543",
        })

        payload = {
            "verification_id": session_id,
            "document_type": "visa",
        }
        resp = client.post("/api/v1/verification/registry", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["registry"]["status"] == "MATCHED"
        assert data["provider_metadata"]["source_type"] == "development_mock"

    def test_risk_visa_endpoint(self):
        from app.services.risk.risk_session_store import risk_session_store
        session_id = "test-api-visa-risk-1"
        risk_session_store.update_module(session_id, "m2_validation", {
            "status": "passed",
            "summary": "Visa validation passed",
            "checks": {
                "required_fields": {"valid": True, "status": "passed"},
                "expiry_date": {"valid": True, "status": "passed", "expired": False},
            },
        })
        risk_session_store.update_module(session_id, "m5_registry", {
            "registry": {"status": "MATCHED"},
            "field_results": [],
            "provider_metadata": {"source_type": "development_mock"},
        })

        payload = {
            "verification_id": session_id,
            "document_type": "visa",
        }
        resp = client.post("/api/v1/verification/risk", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "risk_assessment" in data
        assert data["risk_assessment"]["risk_score"] < 30
        assert data["risk_assessment"]["risk_level"] in ("LOW", "NEGLIGIBLE")

    def test_unsupported_document_rejected_with_422(self):
        if not SAMPLE_VISA_PATH.exists():
            pytest.skip("sample_visa.jpg not generated")

        from app.services.documents.profiles.document_profile import DocumentProfile, ProfileStatus
        from app.services.documents.profiles.document_profile_registry import document_profile_registry
        dummy = DocumentProfile(document_type="consular_id", display_name="Consular ID", status=ProfileStatus.COMING_SOON)
        document_profile_registry.register(dummy)

        with open(SAMPLE_VISA_PATH, "rb") as f:
            files = {"file": ("sample.jpg", f, "image/jpeg")}
            data = {"document_type": "consular_id"}
            resp = client.post("/api/v1/verification/ocr", files=files, data=data)

        assert resp.status_code == 422
        assert "not yet supported" in resp.json()["detail"].lower()

    def test_unknown_document_rejected_with_404(self):
        if not SAMPLE_VISA_PATH.exists():
            pytest.skip("sample_visa.jpg not generated")

        with open(SAMPLE_VISA_PATH, "rb") as f:
            files = {"file": ("sample.jpg", f, "image/jpeg")}
            data = {"document_type": "alien_card_unknown"}
            resp = client.post("/api/v1/verification/ocr", files=files, data=data)

        assert resp.status_code == 404
        assert "unknown document type" in resp.json()["detail"].lower()
