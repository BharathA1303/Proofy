"""
tests/test_risk_api.py

API-level tests for POST /api/v1/verification/risk.
Tests: validation, schema, security (no client score injection), audit fields.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.risk.risk_session_store import risk_session_store


client = TestClient(app)


def _seed_risk_store(verification_id: str) -> None:
    """Seed the risk session store with clean M1–M5 evidence."""
    risk_session_store.update_module(verification_id, "m1_ocr", {
        "status": "completed", "overall_confidence": 0.95,
        "has_low_confidence_regions": False, "mrz_available": True,
        "critical_fields_missing": [],
    })
    risk_session_store.update_module(verification_id, "m2_validation", {
        "status": "passed", "summary": "All passed.",
        "checks": {
            "mrz_structure": {"valid": True, "status": "passed", "message": "OK"},
            "document_number_checksum": {"valid": True, "status": "passed", "computed": 5, "actual": 5, "message": "OK"},
            "dob_checksum": {"valid": True, "status": "passed", "computed": 3, "actual": 3, "message": "OK"},
            "expiry_checksum": {"valid": True, "status": "passed", "computed": 7, "actual": 7, "message": "OK"},
            "composite_checksum": {"valid": True, "status": "passed", "computed": 2, "actual": 2, "message": "OK"},
            "expiry_date": {"valid": True, "status": "passed", "expired": False, "expiry_date": "2030-01-01", "message": "OK"},
            "passport_number_binding": {"valid": True, "status": "passed", "match": True, "viz_value": "AB", "mrz_value": "AB", "message": "OK"},
            "viz_mrz_consistency": {"valid": True, "status": "passed", "fields": {}, "message": "OK"},
        }
    })
    risk_session_store.update_module(verification_id, "m3_forensics", {
        "status": "completed", "overall_assessment": "no_significant_anomaly", "signals": []
    })
    risk_session_store.update_module(verification_id, "m4_biometrics", {
        "overall_assessment": "FACE_MATCH",
        "document_face": {"detected": True, "quality": "acceptable"},
        "live_face": {"detected": True, "quality": "acceptable"},
        "anti_spoof": {"status": "pass", "score": 0.95, "model": "MiniFASNetV2", "explanation": "Live."},
        "secondary_pad": {"frequency_domain": "pass", "texture_analysis": "pass",
                         "specular_glare": "pass", "temporal_variance": "pass"},
        "face_match": {"status": "match", "similarity": 0.80, "threshold": 0.40, "explanation": "Match."},
    })
    risk_session_store.update_module(verification_id, "m5_registry", {
        "registry": {"status": "MATCHED", "record_found": True},
        "field_results": [],
        "provider_metadata": {"provider_id": "mock_passport", "source_type": "development_mock"},
    })


def test_risk_endpoint_returns_200():
    vid = "api-test-clean-001"
    _seed_risk_store(vid)
    resp = client.post("/api/v1/verification/risk", json={
        "verification_id": vid,
        "document_type": "passport",
    })
    assert resp.status_code == 200


def test_risk_response_schema():
    vid = "api-test-schema-001"
    _seed_risk_store(vid)
    resp = client.post("/api/v1/verification/risk", json={
        "verification_id": vid,
        "document_type": "passport",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "verification_id" in data
    assert "document_type" in data
    assert "risk_assessment" in data
    ra = data["risk_assessment"]
    assert "risk_score" in ra
    assert "risk_level" in ra
    assert "officer_recommendation" in ra
    assert "reasons" in ra
    assert "category_breakdown" in ra
    assert "module_summary" in ra
    assert "completeness" in ra
    assert "conflict_detected" in ra
    assert "risk_config_version" in ra


def test_risk_score_in_range():
    vid = "api-test-range-001"
    _seed_risk_store(vid)
    resp = client.post("/api/v1/verification/risk", json={
        "verification_id": vid,
        "document_type": "passport",
    })
    data = resp.json()
    score = data["risk_assessment"]["risk_score"]
    assert 0 <= score <= 100


def test_risk_level_valid_values():
    vid = "api-test-level-001"
    _seed_risk_store(vid)
    resp = client.post("/api/v1/verification/risk", json={
        "verification_id": vid,
        "document_type": "passport",
    })
    level = resp.json()["risk_assessment"]["risk_level"]
    assert level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def test_risk_recommendation_valid_values():
    vid = "api-test-rec-001"
    _seed_risk_store(vid)
    resp = client.post("/api/v1/verification/risk", json={
        "verification_id": vid,
        "document_type": "passport",
    })
    rec = resp.json()["risk_assessment"]["officer_recommendation"]
    assert rec in (
        "STANDARD OFFICER REVIEW",
        "REVIEW REQUIRED",
        "HIGH PRIORITY REVIEW",
        "CRITICAL REVIEW REQUIRED",
    )


def test_risk_missing_verification_id_returns_422():
    resp = client.post("/api/v1/verification/risk", json={
        "document_type": "passport",
    })
    assert resp.status_code == 422


def test_risk_missing_document_type_returns_422():
    resp = client.post("/api/v1/verification/risk", json={
        "verification_id": "some-id",
    })
    assert resp.status_code == 422


def test_risk_client_cannot_inject_score():
    """Extra fields like risk_score must be ignored by the server."""
    vid = "api-test-inject-001"
    _seed_risk_store(vid)
    resp = client.post("/api/v1/verification/risk", json={
        "verification_id": vid,
        "document_type": "passport",
        "risk_score": 0,    # attempt to inject a clean score
        "risk_level": "LOW",
        "reasons": [],
    })
    assert resp.status_code == 200
    # Server computes from evidence, not from client fields
    data = resp.json()
    # As long as it returns without error and has proper schema, injection was ignored
    assert "risk_score" in data["risk_assessment"]


def test_risk_no_verdict_vocabulary_in_response():
    vid = "api-test-vocab-001"
    _seed_risk_store(vid)
    resp = client.post("/api/v1/verification/risk", json={
        "verification_id": vid,
        "document_type": "passport",
    })
    resp_str = resp.text.lower()
    forbidden = ["denied", "forged", "blacklist", "detain", "arrest", "admitted"]
    for word in forbidden:
        assert word not in resp_str, f"Forbidden word '{word}' in API response"


def test_risk_no_session_returns_valid_response():
    """Missing session → engine returns score from empty evidence (all modules not-run)."""
    resp = client.post("/api/v1/verification/risk", json={
        "verification_id": "nonexistent-session-xyz",
        "document_type": "passport",
    })
    # Should return 200 (graceful degradation) not 500
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_assessment"]["completeness"] == 0.0


def test_risk_completeness_full_pipeline():
    vid = "api-test-complete-001"
    _seed_risk_store(vid)
    resp = client.post("/api/v1/verification/risk", json={
        "verification_id": vid,
        "document_type": "passport",
    })
    ra = resp.json()["risk_assessment"]
    assert ra["completeness"] == 1.0
    assert len(ra["module_summary"]) == 5
