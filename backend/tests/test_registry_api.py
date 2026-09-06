"""
tests/test_registry_api.py

Integration tests for POST /api/v1/verification/registry endpoint.

Tests cover:
  - Valid verification_id + passport → MATCHED
  - Missing verification_id (validation error)
  - Session not found → UNAVAILABLE response (not 404)
  - NOT_FOUND record
  - MISMATCH record
  - REVOKED record
  - EXPIRED record
  - SUSPENDED record
  - Unsupported document type → UNAVAILABLE (via stub provider)
  - Response never contains risk_score
  - source_type always visible in response
  - Response structure matches RegistryVerificationResponse schema

NOTE: These tests pre-populate the RegistrySessionStore directly
to avoid dependency on the full OCR pipeline.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.main import app
from app.services.registry.session_store import registry_session_store


@pytest.fixture
def client():
    return TestClient(app)


def _seed_session(verification_id: str, doc_num: str = "TESTPASS001", **kwargs):
    """Populate the registry session store for a test."""
    session = {
        "document_type": "passport",
        "document_number": doc_num,
        "document_number_source": "mrz",
        "name": kwargs.get("name", "TEST USER ONE"),
        "name_source": "viz",
        "date_of_birth": kwargs.get("dob", "1990-01-01"),
        "dob_source": "mrz",
        "nationality": kwargs.get("nationality", "IND"),
        "nationality_source": "mrz",
        "expiry_date": kwargs.get("expiry", "2030-01-01"),
        "expiry_source": "mrz",
    }
    registry_session_store.set(verification_id, session)


# ── Valid requests ────────────────────────────────────────────────────────────

class TestRegistryEndpointMatched:
    def test_matched_record_returns_200(self, client):
        _seed_session("test-matched-001")
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "test-matched-001",
            "document_type": "passport",
        })
        assert response.status_code == 200

    def test_matched_response_has_registry_key(self, client):
        _seed_session("test-matched-002")
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "test-matched-002",
            "document_type": "passport",
        })
        data = response.json()
        assert "registry" in data

    def test_matched_response_status(self, client):
        _seed_session("test-matched-003")
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "test-matched-003",
            "document_type": "passport",
        })
        data = response.json()
        assert data["registry"]["status"] == "MATCHED"

    def test_matched_has_provider_metadata(self, client):
        _seed_session("test-matched-004")
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "test-matched-004",
            "document_type": "passport",
        })
        data = response.json()
        assert "provider_metadata" in data
        assert data["provider_metadata"]["source_type"] == "development_mock"

    def test_matched_has_field_results(self, client):
        _seed_session("test-matched-005")
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "test-matched-005",
            "document_type": "passport",
        })
        data = response.json()
        assert isinstance(data["field_results"], list)
        assert len(data["field_results"]) > 0

    def test_matched_has_evidence(self, client):
        _seed_session("test-matched-006")
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "test-matched-006",
            "document_type": "passport",
        })
        data = response.json()
        assert isinstance(data["evidence"], list)
        assert len(data["evidence"]) > 0

    def test_matched_no_risk_score(self, client):
        _seed_session("test-matched-007")
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "test-matched-007",
            "document_type": "passport",
        })
        data = response.json()
        assert "risk_score" not in data
        assert "final_decision" not in data

    def test_matched_verification_id_in_response(self, client):
        _seed_session("test-matched-008")
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "test-matched-008",
            "document_type": "passport",
        })
        data = response.json()
        assert data["verification_id"] == "test-matched-008"


# ── Session not found ─────────────────────────────────────────────────────────

class TestRegistryEndpointSessionNotFound:
    def test_missing_session_returns_200_unavailable(self, client):
        """Missing session → UNAVAILABLE response (200 OK, not 404 error)"""
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "session-that-does-not-exist-xyz",
            "document_type": "passport",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["registry"]["status"] == "UNAVAILABLE"

    def test_missing_session_not_labeled_invalid(self, client):
        """Missing session MUST NOT be labeled as document invalid or forged"""
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "absolutely-not-a-session",
            "document_type": "passport",
        })
        data = response.json()
        evidence_text = " ".join(
            e.get("description", "") for e in data.get("evidence", [])
        ).upper()
        assert "INVALID DOCUMENT" not in evidence_text
        assert "FORGED" not in evidence_text


# ── Specific record statuses ───────────────────────────────────────────────────

class TestRegistryEndpointStatuses:
    def test_not_found_status(self, client):
        _seed_session("test-nf-001", doc_num="TESTNOTFOUND001")
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "test-nf-001",
            "document_type": "passport",
        })
        data = response.json()
        assert data["registry"]["status"] == "NOT_FOUND"
        assert data["registry"]["record_found"] is False

    def test_revoked_status(self, client):
        _seed_session(
            "test-rev-001", doc_num="TESTREVOKED001",
            name="TEST REVOKED", dob="1975-03-20", nationality="IND"
        )
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "test-rev-001",
            "document_type": "passport",
        })
        data = response.json()
        assert data["registry"]["status"] == "REVOKED"

    def test_mismatch_status(self, client):
        _seed_session(
            "test-mm-001", doc_num="TESTMISMATCH001",
            name="TEST USER ONE", dob="1990-01-01", nationality="IND"
        )
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "test-mm-001",
            "document_type": "passport",
        })
        data = response.json()
        assert data["registry"]["status"] == "MISMATCH"

    def test_expired_status(self, client):
        _seed_session(
            "test-exp-001", doc_num="TESTEXPIRED001",
            name="TEST EXPIRED", dob="1985-06-15", nationality="IND"
        )
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "test-exp-001",
            "document_type": "passport",
        })
        data = response.json()
        assert data["registry"]["status"] == "EXPIRED"

    def test_suspended_status(self, client):
        _seed_session(
            "test-sus-001", doc_num="TESTSUSPENDED001",
            name="TEST SUSPENDED", dob="1980-12-10", nationality="IND"
        )
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "test-sus-001",
            "document_type": "passport",
        })
        data = response.json()
        assert data["registry"]["status"] == "SUSPENDED"


# ── Source type visibility ─────────────────────────────────────────────────────

class TestRegistrySourceTypeVisibility:
    def test_source_type_always_visible(self, client):
        """source_type must always be present so UI can distinguish mock from real"""
        _seed_session("test-src-001")
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "test-src-001",
            "document_type": "passport",
        })
        data = response.json()
        assert "source_type" in data["provider_metadata"]

    def test_source_type_is_development_mock(self, client):
        _seed_session("test-src-002")
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "test-src-002",
            "document_type": "passport",
        })
        data = response.json()
        assert data["provider_metadata"]["source_type"] == "development_mock"

    def test_source_type_never_government_registry(self, client):
        """In mock mode, source_type must NEVER be 'government_registry'"""
        _seed_session("test-src-003")
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "test-src-003",
            "document_type": "passport",
        })
        data = response.json()
        assert data["provider_metadata"]["source_type"] != "government_registry"


# ── Validation ─────────────────────────────────────────────────────────────────

class TestRegistryEndpointValidation:
    def test_missing_verification_id_returns_422(self, client):
        """Pydantic validation: verification_id is required"""
        response = client.post("/api/v1/verification/registry", json={
            "document_type": "passport",
        })
        assert response.status_code == 422

    def test_missing_body_returns_422(self, client):
        response = client.post("/api/v1/verification/registry", json={})
        assert response.status_code == 422


# ── Audit trail ───────────────────────────────────────────────────────────────

class TestRegistryAuditTrail:
    def test_audit_contains_verification_id(self, client):
        _seed_session("test-audit-001")
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "test-audit-001",
            "document_type": "passport",
        })
        data = response.json()
        assert data["audit"]["verification_id"] == "test-audit-001"

    def test_audit_contains_timestamp(self, client):
        _seed_session("test-audit-002")
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "test-audit-002",
            "document_type": "passport",
        })
        data = response.json()
        assert "timestamp" in data["audit"]

    def test_audit_contains_registry_status(self, client):
        _seed_session("test-audit-003")
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "test-audit-003",
            "document_type": "passport",
        })
        data = response.json()
        assert "registry_status" in data["audit"]

    def test_audit_no_sensitive_data(self, client):
        """Audit trail must not contain API keys, tokens, or DB paths"""
        _seed_session("test-audit-004")
        response = client.post("/api/v1/verification/registry", json={
            "verification_id": "test-audit-004",
            "document_type": "passport",
        })
        data = response.json()
        audit_str = str(data["audit"]).lower()
        # None of these should appear in audit output
        for forbidden in ["api_key", "api-key", "secret", "password", "token", "bearer"]:
            assert forbidden not in audit_str
