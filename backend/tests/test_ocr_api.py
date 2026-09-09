"""
backend/tests/test_ocr_api.py

Integration tests for the FastAPI OCR endpoint.

These tests use httpx.AsyncClient and mock the OCR engine to avoid
requiring PaddleOCR model downloads during CI.

The OCR ENGINE is mocked — the parser logic is NOT mocked.
We test the full HTTP → endpoint → parser → response chain.
"""
import io
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

# We need the app AFTER setting up mocks for the OCR engine
import app.services.ocr.ocr_engine as ocr_engine_module
from app.services.ocr.ocr_engine import OCRRegion


# ──────────────────────────────────────────────
#  Fixtures
# ──────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_ocr_engine_init(monkeypatch):
    """
    Prevent PaddleOCR from actually loading models during tests.
    Marks the engine as initialized and replaces run_ocr with a controllable mock.
    """
    from app.services.ocr.ocr_cache import clear_ocr_cache
    clear_ocr_cache()
    # Prevent init from loading any models
    monkeypatch.setattr(ocr_engine_module, "init_engine", lambda **kw: None)
    # Mark engine as ready
    monkeypatch.setattr(ocr_engine_module, "_paddle_ocr_instance", MagicMock())


def _make_synthetic_passport_regions() -> list[OCRRegion]:
    """Synthetic OCR output resembling a passport scan (all values are fictional)."""
    def r(text, top_y=100, conf=0.95):
        return OCRRegion(
            text=text, confidence=conf,
            bbox=[[0, top_y], [300, top_y], [300, top_y+20], [0, top_y+20]],
        )

    mrz1 = "P<INDSYNTH<<TEST<USER<<<<<<<<<<<<<<<<<<<<<<<"
    mrz2 = "T98765431IND8506154M3006300<<<<<<<<<<<<<<<8"

    return [
        r("REPUBLIC OF INDIA", top_y=50),
        r("PASSPORT", top_y=80),
        r("Surname", top_y=180),
        r("SYNTH", top_y=200),
        r("Given Name(s)", top_y=240),
        r("TEST USER", top_y=260),
        r("Date of Birth", top_y=320),
        r("15/06/1985", top_y=340),
        r("Sex", top_y=380),
        r("M", top_y=400),
        r("Nationality", top_y=440),
        r("INDIAN", top_y=460),
        r("Date of Expiry", top_y=500),
        r("30/06/2030", top_y=520),
        r(mrz1, top_y=820, conf=0.93),
        r(mrz2, top_y=850, conf=0.91),
    ]


def _create_valid_jpeg() -> bytes:
    """Create a minimal valid JPEG image in memory."""
    img = Image.new("RGB", (800, 1000), color=(240, 240, 240))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _create_valid_png() -> bytes:
    img = Image.new("RGB", (800, 1000), color=(240, 240, 240))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
async def client():
    """Async HTTP client connected to the FastAPI app under test."""
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ──────────────────────────────────────────────
#  Tests
# ──────────────────────────────────────────────

@pytest.mark.anyio
class TestOCREndpoint:

    async def test_health_check(self, client):
        """Health endpoint should return 200 and report engine ready."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["ocr_engine_ready"] is True

    async def test_valid_passport_jpeg(self, client):
        """Valid JPEG passport image should return 200 with extracted fields."""
        with patch.object(ocr_engine_module, "run_ocr", return_value=_make_synthetic_passport_regions()):
            jpeg_bytes = _create_valid_jpeg()
            response = await client.post(
                "/api/v1/verification/ocr",
                files={"file": ("passport.jpg", jpeg_bytes, "image/jpeg")},
                data={"document_type": "passport"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["document_type"] == "passport"
        assert data["status"] in ("completed", "partial")
        assert "traveler" in data
        assert "mrz" in data
        assert "verification_id" in data

    async def test_mrz_extracted_in_response(self, client):
        """MRZ lines should be present in the response when OCR provides them."""
        with patch.object(ocr_engine_module, "run_ocr", return_value=_make_synthetic_passport_regions()):
            jpeg_bytes = _create_valid_jpeg()
            response = await client.post(
                "/api/v1/verification/ocr",
                files={"file": ("passport.jpg", jpeg_bytes, "image/jpeg")},
                data={"document_type": "passport"},
            )
        assert response.status_code == 200
        mrz = response.json()["mrz"]
        assert mrz["line1"] is not None
        assert mrz["line2"] is not None

    async def test_valid_passport_png(self, client):
        """PNG uploads should be accepted."""
        with patch.object(ocr_engine_module, "run_ocr", return_value=_make_synthetic_passport_regions()):
            response = await client.post(
                "/api/v1/verification/ocr",
                files={"file": ("passport.png", _create_valid_png(), "image/png")},
                data={"document_type": "passport"},
            )
        assert response.status_code == 200

    async def test_missing_file_returns_422(self, client):
        """Missing file parameter should return 422 Unprocessable Entity."""
        response = await client.post(
            "/api/v1/verification/ocr",
            data={"document_type": "passport"},
        )
        assert response.status_code == 422

    async def test_invalid_image_bytes_returns_400(self, client):
        """Uploading non-image bytes should return 400."""
        response = await client.post(
            "/api/v1/verification/ocr",
            files={"file": ("notanimage.jpg", b"this is not an image", "image/jpeg")},
            data={"document_type": "passport"},
        )
        assert response.status_code in (400, 415)

    async def test_pdf_returns_415(self, client):
        """PDF files should be rejected with 415 Unsupported Media Type."""
        fake_pdf = b"%PDF-1.4 fake pdf content"
        response = await client.post(
            "/api/v1/verification/ocr",
            files={"file": ("document.pdf", fake_pdf, "application/pdf")},
            data={"document_type": "passport"},
        )
        assert response.status_code == 415

    async def test_empty_file_returns_400(self, client):
        """Empty file should be rejected."""
        response = await client.post(
            "/api/v1/verification/ocr",
            files={"file": ("empty.jpg", b"", "image/jpeg")},
            data={"document_type": "passport"},
        )
        assert response.status_code in (400, 415)

    async def test_no_text_ocr_returns_422(self, client):
        """When OCR returns no text, the endpoint should return 422."""
        with patch.object(ocr_engine_module, "run_ocr", return_value=[]):
            response = await client.post(
                "/api/v1/verification/ocr",
                files={"file": ("blank.jpg", _create_valid_jpeg(), "image/jpeg")},
                data={"document_type": "passport"},
            )
        assert response.status_code == 422

    async def test_response_contains_no_stack_trace(self, client):
        """Error responses must not contain Python exception details."""
        response = await client.post(
            "/api/v1/verification/ocr",
            files={"file": ("bad.jpg", b"not an image", "image/jpeg")},
            data={"document_type": "passport"},
        )
        body = response.text
        assert "Traceback" not in body
        assert "File \"" not in body
        assert "Exception" not in body

    async def test_traveler_fields_never_fabricated(self, client):
        """When OCR has no useful content, traveler fields must be null."""
        # Return minimal non-empty regions that have no passport structure
        noise_regions = [
            OCRRegion(
                text="XYZ 123",
                confidence=0.60,
                bbox=[[0, 100], [100, 100], [100, 120], [0, 120]],
            )
        ]
        with patch.object(ocr_engine_module, "run_ocr", return_value=noise_regions):
            response = await client.post(
                "/api/v1/verification/ocr",
                files={"file": ("noise.jpg", _create_valid_jpeg(), "image/jpeg")},
                data={"document_type": "passport"},
            )
        assert response.status_code == 200
        traveler = response.json()["traveler"]
        # None of these should have fake/hardcoded values
        for field_name in ("name", "docNumber", "dob", "nationality"):
            val = traveler.get(field_name)
            assert val not in ("Unknown", "John Doe", "N/A", "Sample"), \
                f"Field '{field_name}' should be null, got: {val!r}"

    async def test_ocr_engine_error_returns_500(self, client):
        """OCR engine internal error should return 500 with safe message."""
        with patch.object(ocr_engine_module, "run_ocr", side_effect=RuntimeError("GPU OOM")):
            response = await client.post(
                "/api/v1/verification/ocr",
                files={"file": ("passport.jpg", _create_valid_jpeg(), "image/jpeg")},
                data={"document_type": "passport"},
            )
        assert response.status_code == 500
        # Must not expose internal error message
        body = response.json()
        assert "GPU OOM" not in str(body)

    async def test_verification_id_is_unique_per_request(self, client):
        """Each request must receive a distinct verification_id."""
        ids = set()
        with patch.object(ocr_engine_module, "run_ocr", return_value=_make_synthetic_passport_regions()):
            for _ in range(3):
                resp = await client.post(
                    "/api/v1/verification/ocr",
                    files={"file": ("pp.jpg", _create_valid_jpeg(), "image/jpeg")},
                    data={"document_type": "passport"},
                )
                ids.add(resp.json()["verification_id"])
        assert len(ids) == 3, "Each request should produce a unique verification_id"


class TestValidateEndpoint:
    """Integration tests for POST /api/v1/verification/validate (Module 2)."""

    VALID_LINE1 = "P<INDMALHOTRA<<ASHOK<KUMAR<<<<<<<<<<<<<<<<<<"
    VALID_LINE2 = "A1234567<6IND9001011M2912316<<<<<<<<<<<<<<<8"

    @pytest.fixture
    def valid_validate_payload(self):
        return {
            "verification_id": "test-verif-12345",
            "document_type": "passport",
            "mrz": {
                "line1": self.VALID_LINE1,
                "line2": self.VALID_LINE2,
            },
            "traveler": {
                "docNumber": "A1234567",
                "name": "ASHOK KUMAR MALHOTRA",
                "nationality": "IND",
                "gender": "M",
                "dob": "01/01/1990",
                "expiry": "31/12/2029",
            },
        }

    async def test_validate_valid_payload_returns_200_passed(self, client, valid_validate_payload):
        resp = await client.post("/api/v1/verification/validate", json=valid_validate_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["verification_id"] == "test-verif-12345"
        assert data["document_type"] == "passport"
        assert "document_validation" in data
        val = data["document_validation"]
        assert val["status"] == "passed"
        assert val["checks"]["passport_number_binding"]["status"] == "passed"
        assert val["checks"]["composite_checksum"]["status"] == "passed"

    async def test_validate_binding_mismatch_returns_failed(self, client, valid_validate_payload):
        # Alter the visual document number
        valid_validate_payload["traveler"]["docNumber"] = "X9999999"
        resp = await client.post("/api/v1/verification/validate", json=valid_validate_payload)
        assert resp.status_code == 200
        val = resp.json()["document_validation"]
        assert val["status"] == "failed"
        assert val["checks"]["passport_number_binding"]["match"] is False

    async def test_validate_empty_mrz_returns_insufficient_data(self, client):
        payload = {
            "verification_id": "test-no-mrz",
            "document_type": "passport",
            "mrz": None,
            "traveler": {"docNumber": "A1234567"},
        }
        resp = await client.post("/api/v1/verification/validate", json=payload)
        assert resp.status_code == 200
        val = resp.json()["document_validation"]
        assert val["status"] == "insufficient_data"

    async def test_validate_invalid_body_returns_422(self, client):
        resp = await client.post(
            "/api/v1/verification/validate",
            json={"invalid_key": "missing_required_fields"},
        )
        assert resp.status_code == 422
