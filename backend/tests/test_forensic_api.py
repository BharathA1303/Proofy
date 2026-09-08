"""
backend/tests/test_forensic_api.py

Integration tests for the FastAPI /api/v1/verification/forensic endpoint.

The OCR engine is mocked (never loaded) since this endpoint does not use it,
but app.main imports it at module load time.
"""
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

import app.services.ocr.ocr_engine as ocr_engine_module
from tests.forensic_test_utils import (
    encode_jpeg,
    make_dark,
    make_textured_image,
    make_tiny,
)


@pytest.fixture(autouse=True)
def mock_ocr_engine_init(monkeypatch):
    monkeypatch.setattr(ocr_engine_module, "init_engine", lambda **kw: None)
    monkeypatch.setattr(ocr_engine_module, "_paddle_ocr_instance", MagicMock())


@pytest.fixture
async def client():
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
class TestForensicEndpoint:
    async def test_valid_image_returns_completed_analysis(self, client):
        img = make_textured_image()
        jpeg_bytes = encode_jpeg(img, quality=90)

        response = await client.post(
            "/api/v1/verification/forensic",
            files={"file": ("passport.jpg", jpeg_bytes, "image/jpeg")},
            data={"document_type": "passport", "verification_id": "test-vid-1"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["verification_id"] == "test-vid-1"
        forensic = data["forensic_analysis"]
        assert forensic["status"] == "completed"
        assert forensic["overall_assessment"] in (
            "no_significant_anomaly", "suspicious", "high_forensic_concern",
        )
        assert isinstance(forensic["signals"], list)
        assert len(forensic["signals"]) == 5

        for signal in forensic["signals"]:
            assert signal["status"] not in ("forged", "fake")
            assert "confidence" in signal

    async def test_low_quality_image_returns_insufficient_data(self, client):
        img = make_tiny(make_dark(make_textured_image(), factor=0.03), size=(80, 100))
        jpeg_bytes = encode_jpeg(img, quality=90)

        response = await client.post(
            "/api/v1/verification/forensic",
            files={"file": ("passport.jpg", jpeg_bytes, "image/jpeg")},
            data={"document_type": "passport", "verification_id": "test-vid-2"},
        )

        assert response.status_code == 200
        forensic = response.json()["forensic_analysis"]
        assert forensic["status"] == "insufficient_data"
        assert forensic["overall_assessment"] == "insufficient_data"
        assert forensic["signals"] == []

    async def test_never_returns_final_decision_fields(self, client):
        img = make_textured_image()
        jpeg_bytes = encode_jpeg(img, quality=90)

        response = await client.post(
            "/api/v1/verification/forensic",
            files={"file": ("passport.jpg", jpeg_bytes, "image/jpeg")},
            data={"document_type": "passport", "verification_id": "test-vid-3"},
        )

        data = response.json()
        assert "risk_score" not in data
        assert "final_decision" not in data
        assert "face_match" not in data
        assert "risk_score" not in data["forensic_analysis"]

    async def test_unsupported_file_type_rejected(self, client):
        response = await client.post(
            "/api/v1/verification/forensic",
            files={"file": ("passport.txt", b"not an image", "text/plain")},
            data={"document_type": "passport", "verification_id": "test-vid-4"},
        )
        assert response.status_code == 415
