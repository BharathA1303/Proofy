"""
tests/test_case_api.py

API integration tests for Multi-Document Verification Cases & Cross-Document Intelligence.
Tests:
- POST /api/v1/verification/case (create case)
- GET  /api/v1/verification/case/{case_id} (get case summary)
- POST /api/v1/verification/case/{case_id}/documents (add documents)
- POST /api/v1/verification/case/{case_id}/evaluate (re-evaluate relationships)
- POST /api/v1/verification/case/risk (calculate case-level composite risk)
- DELETE /api/v1/verification/case/{case_id}/documents/{doc_id} (remove document)
- 404 for unknown case
- Duplicate document error
- Client evidence injection immunity
"""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.services.ocr.ocr_engine as ocr_engine_module
from app.services.ocr.ocr_engine import OCRRegion
from tests.forensic_test_utils import encode_jpeg, make_textured_image

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_ocr(monkeypatch):
    """Prevent loading neural OCR models during API tests."""
    monkeypatch.setattr(ocr_engine_module, "init_engine", lambda **kw: None)
    monkeypatch.setattr(ocr_engine_module, "_paddle_ocr_instance", MagicMock())


def _make_dummy_image() -> bytes:
    img = make_textured_image(800, 600)
    return encode_jpeg(img)


class TestCaseApi:
    """API endpoint verification for Case and Cross-Document Intelligence."""

    def test_create_and_get_case(self):
        # 1. Create Case
        res = client.post("/api/v1/verification/case", json={"notes": "Border test case"})
        assert res.status_code == 201
        data = res.json()
        case_id = data["case_id"]
        assert case_id.startswith("CASE-")
        assert data["status"] == "active"
        assert len(data["documents"]) == 0

        # 2. Get Case
        res_get = client.get(f"/api/v1/verification/case/{case_id}")
        assert res_get.status_code == 200
        get_data = res_get.json()
        assert get_data["case_id"] == case_id
        assert get_data["notes"] == "Border test case"

    def test_get_nonexistent_case_returns_404(self):
        res = client.get("/api/v1/verification/case/CASE-NOT-EXIST")
        assert res.status_code == 404

    def test_add_passport_and_visa_and_evaluate_risk(self, monkeypatch):
        # Mock OCR output for passport and visa
        def mock_passport_ocr(*args, **kwargs):
            return [
                OCRRegion(text="P<USADOE<<JOHN<<<<<<<<<<<<<<<<<<<<<<<<<<<", confidence=0.98, bbox=[[0, 10], [100, 10], [100, 30], [0, 30]]),
                OCRRegion(text="T9876543<8USA9006158M2501015<<<<<<<<<<<6", confidence=0.98, bbox=[[0, 40], [100, 40], [100, 60], [0, 60]]),
            ]

        def mock_visa_ocr(*args, **kwargs):
            return [
                OCRRegion(text="VN987654321", confidence=0.95, bbox=[[0, 10], [100, 10], [100, 30], [0, 30]]),
                OCRRegion(text="PASSPORT NUMBER: T9876543", confidence=0.95, bbox=[[0, 40], [100, 40], [100, 60], [0, 60]]),
                OCRRegion(text="DOE, JOHN", confidence=0.95, bbox=[[0, 70], [100, 70], [100, 90], [0, 90]]),
            ]

        # 1. Create Case
        create_res = client.post("/api/v1/verification/case", json={})
        case_id = create_res.json()["case_id"]

        # 2. Add Passport
        monkeypatch.setattr(ocr_engine_module, "run_ocr", mock_passport_ocr)
        img_bytes = _make_dummy_image()
        res_p = client.post(
            f"/api/v1/verification/case/{case_id}/documents",
            data={"document_type": "passport"},
            files={"file": ("passport.jpg", img_bytes, "image/jpeg")},
        )
        assert res_p.status_code == 201
        data_p = res_p.json()
        assert len(data_p["documents"]) == 1
        assert data_p["documents"][0]["document_type"] == "passport"

        # 3. Add Visa
        monkeypatch.setattr(ocr_engine_module, "run_ocr", mock_visa_ocr)
        res_v = client.post(
            f"/api/v1/verification/case/{case_id}/documents",
            data={"document_type": "visa"},
            files={"file": ("visa.jpg", img_bytes, "image/jpeg")},
        )
        assert res_v.status_code == 201
        data_v = res_v.json()
        assert len(data_v["documents"]) == 2

        # Cross-document analysis should have run automatically
        assert len(data_v["relationships"]) > 0

        # 4. Trigger Evaluate Endpoint
        eval_res = client.post(f"/api/v1/verification/case/{case_id}/evaluate")
        assert eval_res.status_code == 200
        eval_data = eval_res.json()
        assert len(eval_data["relationships"]) > 0

        # 5. Trigger Risk Endpoint
        risk_res = client.post("/api/v1/verification/case/risk", json={"case_id": case_id})
        assert risk_res.status_code == 200
        risk_data = risk_res.json()
        assert "risk_assessment" in risk_data
        assert "risk_score" in risk_data["risk_assessment"]
        assert "recommendation" in risk_data["risk_assessment"]
        assert len(risk_data["risk_assessment"]["documents_considered"]) == 2

        # 6. Remove Document
        visa_doc_id = [d["document_id"] for d in data_v["documents"] if d["document_type"] == "visa"][0]
        del_res = client.delete(f"/api/v1/verification/case/{case_id}/documents/{visa_doc_id}")
        assert del_res.status_code == 200
        del_data = del_res.json()
        assert len(del_data["documents"]) == 1
        assert len(del_data["relationships"]) == 0
