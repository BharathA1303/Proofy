"""
backend/tests/test_document_quality.py

Unit and integration tests for the Pre-OCR Document Quality Gate.
"""
import io
import cv2
import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.services.quality.document_quality import evaluate_document_quality


def _create_synthetic_document(w=850, h=550, brightness=160, blur_ksize=0, add_glare=False, low_contrast=False) -> np.ndarray:
    """Generate a synthetic credential document with realistic text patterns and contours."""
    img = np.full((h, w, 3), brightness, dtype=np.uint8)

    # Draw document border
    cv2.rectangle(img, (20, 20), (w - 20, h - 20), (brightness - 40, brightness - 40, brightness - 40), 3)

    # Draw photo placeholder box
    cv2.rectangle(img, (50, 80), (220, 300), (90, 90, 90), -1)
    cv2.circle(img, (135, 170), 40, (180, 180, 180), -1)

    # Draw simulated text lines (high frequency edges)
    text_color = (brightness - 10, brightness - 10, brightness - 10) if low_contrast else (20, 20, 20)
    for y in range(80, 480, 35):
        cv2.line(img, (260, y), (w - 60, y), text_color, 4)
        cv2.line(img, (260, y + 10), (w - 180, y + 10), text_color, 2)

    # Add specular glare hotspot if requested
    if add_glare:
        cv2.circle(img, (w // 2, h // 2), 90, (255, 255, 255), -1)
        cv2.circle(img, (w // 2, h // 2), 60, (255, 255, 255), -1)

    # Add Gaussian blur if requested
    if blur_ksize > 0:
        img = cv2.GaussianBlur(img, (blur_ksize, blur_ksize), 0)

    return img


class TestDocumentQualityUnit:
    def test_acceptable_document_quality(self):
        doc = _create_synthetic_document(w=900, h=600, brightness=160)
        res = evaluate_document_quality(doc)
        assert res.is_acceptable is True
        assert res.status == "acceptable"
        assert res.overall_score >= 75
        assert res.sharpness_score >= 60
        assert res.resolution_score >= 80
        assert res.error_code is None

    def test_blurry_document_rejected(self):
        # Heavy Gaussian blur reduces Laplacian variance drastically
        blurry = _create_synthetic_document(w=900, h=600, brightness=160, blur_ksize=35)
        res = evaluate_document_quality(blurry)
        assert res.is_acceptable is False
        assert res.status == "poor"
        assert res.sharpness_score < 48
        assert res.error_code == "DOCUMENT_TOO_BLURRY"
        assert "blurry" in res.guidance.lower()

    def test_underexposed_document_rejected(self):
        dark = _create_synthetic_document(w=900, h=600, brightness=20)
        res = evaluate_document_quality(dark)
        assert res.is_acceptable is False
        assert res.status == "poor"
        assert res.brightness_score < 45
        assert res.error_code == "DOCUMENT_TOO_DARK"
        assert "underexposed" in res.guidance.lower() or "brighter" in res.guidance.lower()

    def test_glare_hotspot_rejected(self):
        glare = _create_synthetic_document(w=900, h=600, brightness=140, add_glare=True)
        res = evaluate_document_quality(glare)
        assert res.is_acceptable is False
        assert res.status == "poor"
        assert res.glare_score < 45
        assert res.error_code == "DOCUMENT_GLARE_DETECTED"
        assert "glare" in res.guidance.lower()

    def test_low_resolution_rejected(self):
        small = _create_synthetic_document(w=300, h=200, brightness=160)
        res = evaluate_document_quality(small)
        assert res.is_acceptable is False
        assert res.status == "poor"
        assert res.resolution_score < 48
        assert res.error_code == "DOCUMENT_RESOLUTION_TOO_LOW"
        assert "resolution" in res.guidance.lower()

    def test_empty_or_none_image(self):
        res = evaluate_document_quality(None)
        assert res.is_acceptable is False
        assert res.error_code == "IMAGE_EMPTY"


@pytest.fixture
async def client():
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class TestDocumentQualityAPI:
    @pytest.mark.asyncio
    async def test_quality_check_endpoint_acceptable(self, client: AsyncClient):
        doc_np = _create_synthetic_document(w=900, h=600)
        is_success, buf = cv2.imencode(".jpg", doc_np)
        assert is_success

        files = {"file": ("test_doc.jpg", buf.tobytes(), "image/jpeg")}
        data = {"document_type": "passport"}
        res = await client.post("/api/v1/verification/quality-check", files=files, data=data)
        assert res.status_code == 200
        payload = res.json()
        assert payload["is_acceptable"] is True
        assert payload["overall_score"] >= 75
        assert "metrics" in payload
        assert "sharpness" in payload["metrics"]
        assert "resolution" in payload["metrics"]

    @pytest.mark.asyncio
    async def test_quality_check_endpoint_poor_blur(self, client: AsyncClient):
        blurry_np = _create_synthetic_document(w=900, h=600, blur_ksize=35)
        is_success, buf = cv2.imencode(".jpg", blurry_np)
        assert is_success

        files = {"file": ("blurry_doc.jpg", buf.tobytes(), "image/jpeg")}
        data = {"document_type": "passport"}
        res = await client.post("/api/v1/verification/quality-check", files=files, data=data)
        assert res.status_code == 200
        payload = res.json()
        assert payload["is_acceptable"] is False
        assert payload["status"] == "poor"
        assert payload["error_code"] == "DOCUMENT_TOO_BLURRY"
        assert "blurry" in payload["guidance"].lower()
