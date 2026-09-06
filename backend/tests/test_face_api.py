"""
backend/tests/test_face_api.py

Integration tests for the FastAPI /api/v1/verification/face endpoint.
"""
from unittest.mock import MagicMock
import cv2
import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

import app.services.ocr.ocr_engine as ocr_engine_module
from app.services.face.session_store import session_document_store


def _encode_jpeg(img, quality=90):
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes()


def _create_test_image(w=200, h=250):
    img = np.full((h, w, 3), 130, dtype=np.uint8)
    cv2.circle(img, (w // 2, h // 2), 40, (180, 180, 180), -1)
    return img


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
class TestFaceApi:
    async def test_face_verification_with_cached_session(self, client):
        doc_img = _create_test_image(250, 300)
        doc_bytes = _encode_jpeg(doc_img)
        live_img = _create_test_image(250, 300)
        live_bytes = _encode_jpeg(live_img)

        # Pre-seed session cache as would occur during /ocr or /forensic
        session_id = "test-session-cache-1"
        session_document_store.set(session_id, doc_bytes)

        response = await client.post(
            "/api/v1/verification/face",
            data={"document_type": "passport", "verification_id": session_id},
            files={"live_frame": ("live.jpg", live_bytes, "image/jpeg")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["verification_id"] == session_id
        assert data["document_type"] == "passport"
        assert "document_face" in data
        assert "live_face" in data
        assert "anti_spoof" in data
        assert "face_match" in data
        assert "overall_assessment" in data
        assert "status" in data

    async def test_session_expired_without_fallback_returns_400(self, client):
        live_img = _create_test_image()
        live_bytes = _encode_jpeg(live_img)

        response = await client.post(
            "/api/v1/verification/face",
            data={"document_type": "passport", "verification_id": "non-existent-session-id"},
            files={"live_frame": ("live.jpg", live_bytes, "image/jpeg")},
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert len(data["detail"]) > 0


    async def test_session_expired_with_fallback_document_image(self, client):
        doc_img = _create_test_image()
        doc_bytes = _encode_jpeg(doc_img)
        live_img = _create_test_image()
        live_bytes = _encode_jpeg(live_img)

        session_id = "test-fallback-session-2"

        response = await client.post(
            "/api/v1/verification/face",
            data={"document_type": "passport", "verification_id": session_id},
            files={
                "live_frame": ("live.jpg", live_bytes, "image/jpeg"),
                "document_image": ("doc.jpg", doc_bytes, "image/jpeg"),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["verification_id"] == session_id

    async def test_unsupported_file_format_returns_415(self, client):
        session_id = "test-unsupported-format"
        session_document_store.set(session_id, b"valid-doc-bytes")

        response = await client.post(
            "/api/v1/verification/face",
            data={"document_type": "passport", "verification_id": session_id},
            files={"live_frame": ("live.pdf", b"%PDF-1.4 dummy", "application/pdf")},
        )

        assert response.status_code == 415

    async def test_response_contains_no_sensitive_vectors(self, client):
        doc_img = _create_test_image()
        doc_bytes = _encode_jpeg(doc_img)
        live_img = _create_test_image()
        live_bytes = _encode_jpeg(live_img)

        session_id = "test-privacy-check"
        session_document_store.set(session_id, doc_bytes)

        response = await client.post(
            "/api/v1/verification/face",
            data={"document_type": "passport", "verification_id": session_id},
            files={"live_frame": ("live.jpg", live_bytes, "image/jpeg")},
        )

        assert response.status_code == 200
        text = response.text
        # Security principles: Never leak raw embeddings or raw pixels
        assert "embedding" not in text.lower() or "face_embedding" not in text
        assert "weights" not in text.lower()
        assert "raw_vector" not in text.lower()
