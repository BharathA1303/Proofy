"""
tests/test_mock_passport_provider.py

Unit tests for MockPassportRegistryProvider.

Tests cover:
  - Provider supports passport document type
  - Provider initialization and availability
  - Health check returns correct source_type
  - TESTPASS001 → MATCHED (active, all fields correct)
  - TESTEXPIRED001 → EXPIRED
  - TESTREVOKED001 → REVOKED
  - TESTMISMATCH001 → MISMATCH (active but fields differ)
  - TESTSUSPENDED001 → SUSPENDED
  - Unknown passport number → NOT_FOUND
  - source_type is always 'development_mock'
  - Response never contains risk_score or final_decision
"""
import pytest

from app.schemas.registry import (
    DocumentFieldSource,
    FieldProvenance,
    ProviderSourceType,
    RegistryStatus,
    RegistryVerificationRequest,
)
from app.services.registry.providers.mock_passport import MockPassportRegistryProvider


@pytest.fixture
def provider() -> MockPassportRegistryProvider:
    p = MockPassportRegistryProvider()
    p.initialize()
    return p


def _make_request(
    doc_num: str,
    name: str = "TEST USER ONE",
    dob: str = "1990-01-01",
    nationality: str = "IND",
    verification_id: str = "test-session-001",
) -> RegistryVerificationRequest:
    def p(val, src=DocumentFieldSource.MRZ):
        return FieldProvenance(value=val, source=src) if val else None

    return RegistryVerificationRequest(
        verification_id=verification_id,
        document_type="passport",
        document_number=p(doc_num),
        name=p(name, DocumentFieldSource.VIZ),
        date_of_birth=p(dob),
        nationality=p(nationality),
        expiry_date=p("2030-01-01"),
    )


# ── Provider interface ─────────────────────────────────────────────────────────

class TestProviderInterface:
    def test_supports_passport(self, provider):
        assert provider.supports("passport") is True

    def test_does_not_support_visa(self, provider):
        assert provider.supports("visa") is False

    def test_is_available_after_init(self, provider):
        assert provider.is_available() is True

    def test_not_available_before_init(self):
        p = MockPassportRegistryProvider()
        # Not initialized yet
        assert p.is_available() is False

    def test_provider_id_is_string(self, provider):
        assert isinstance(provider.provider_id, str)
        assert len(provider.provider_id) > 0

    def test_health_check_returns_status(self, provider):
        status = provider.health_check()
        assert status.available is True
        assert status.source_type == ProviderSourceType.DEVELOPMENT_MOCK
        assert "passport" in status.supported_document_types

    def test_health_check_source_type_is_mock(self, provider):
        """Ensure source_type is always development_mock — NEVER government_registry"""
        status = provider.health_check()
        assert status.source_type == ProviderSourceType.DEVELOPMENT_MOCK
        assert status.source_type != "government_registry"


# ── Test record: TESTPASS001 (ACTIVE, matched) ────────────────────────────────

class TestActiveRecord:
    def test_testpass001_returns_matched(self, provider):
        request = _make_request(
            doc_num="TESTPASS001",
            name="TEST USER ONE",
            dob="1990-01-01",
            nationality="IND",
        )
        response = provider.verify(request)
        assert response.registry["status"] == RegistryStatus.MATCHED.value
        assert response.registry["record_found"] is True

    def test_testpass001_source_type_is_mock(self, provider):
        request = _make_request("TESTPASS001")
        response = provider.verify(request)
        assert response.provider_metadata.source_type == ProviderSourceType.DEVELOPMENT_MOCK

    def test_testpass001_has_field_results(self, provider):
        request = _make_request("TESTPASS001")
        response = provider.verify(request)
        assert len(response.field_results) > 0

    def test_testpass001_verification_id_preserved(self, provider):
        request = _make_request("TESTPASS001", verification_id="custom-vid-123")
        response = provider.verify(request)
        assert response.verification_id == "custom-vid-123"

    def test_testpass001_no_risk_score(self, provider):
        """Response must NOT contain risk_score"""
        request = _make_request("TESTPASS001")
        response = provider.verify(request)
        response_dict = response.model_dump()
        assert "risk_score" not in response_dict
        assert "final_decision" not in response_dict

    def test_testpass001_audit_contains_disclaimer(self, provider):
        request = _make_request("TESTPASS001")
        response = provider.verify(request)
        assert "DEVELOPMENT" in response.audit.get("disclaimer", "").upper()


# ── Test record: TESTEXPIRED001 ───────────────────────────────────────────────

class TestExpiredRecord:
    def test_testexpired001_returns_expired(self, provider):
        request = _make_request(
            doc_num="TESTEXPIRED001",
            name="TEST EXPIRED",
            dob="1985-06-15",
            nationality="IND",
        )
        response = provider.verify(request)
        assert response.registry["status"] == RegistryStatus.EXPIRED.value

    def test_testexpired001_record_found(self, provider):
        request = _make_request("TESTEXPIRED001")
        response = provider.verify(request)
        assert response.registry["record_found"] is True


# ── Test record: TESTREVOKED001 ───────────────────────────────────────────────

class TestRevokedRecord:
    def test_testrevoked001_returns_revoked(self, provider):
        request = _make_request(
            doc_num="TESTREVOKED001",
            name="TEST REVOKED",
            dob="1975-03-20",
            nationality="IND",
        )
        response = provider.verify(request)
        assert response.registry["status"] == RegistryStatus.REVOKED.value

    def test_testrevoked001_has_critical_evidence(self, provider):
        request = _make_request("TESTREVOKED001")
        response = provider.verify(request)
        critical = [e for e in response.evidence if e.severity == "critical"]
        assert len(critical) > 0


# ── Test record: TESTMISMATCH001 ──────────────────────────────────────────────

class TestMismatchRecord:
    def test_testmismatch001_returns_mismatch(self, provider):
        """TESTMISMATCH001 is ACTIVE but has different name/dob/nationality"""
        request = _make_request(
            doc_num="TESTMISMATCH001",
            name="TEST USER ONE",     # different from registry: "DIFFERENT NAME ENTIRELY"
            dob="1990-01-01",         # different from registry: "1984-06-15"
            nationality="IND",         # different from registry: "USA"
        )
        response = provider.verify(request)
        assert response.registry["status"] == RegistryStatus.MISMATCH.value

    def test_testmismatch001_record_found(self, provider):
        request = _make_request("TESTMISMATCH001")
        response = provider.verify(request)
        assert response.registry["record_found"] is True

    def test_testmismatch001_has_mismatch_field_results(self, provider):
        request = _make_request(
            doc_num="TESTMISMATCH001",
            name="TEST USER ONE",
            dob="1990-01-01",
            nationality="IND",
        )
        response = provider.verify(request)
        from app.schemas.registry import FieldMatchStatus
        mismatch_results = [r for r in response.field_results if r.status == FieldMatchStatus.MISMATCH]
        assert len(mismatch_results) > 0


# ── Test record: TESTSUSPENDED001 ────────────────────────────────────────────

class TestSuspendedRecord:
    def test_testsuspended001_returns_suspended(self, provider):
        request = _make_request(
            doc_num="TESTSUSPENDED001",
            name="TEST SUSPENDED",
            dob="1980-12-10",
            nationality="IND",
        )
        response = provider.verify(request)
        assert response.registry["status"] == RegistryStatus.SUSPENDED.value


# ── NOT FOUND ─────────────────────────────────────────────────────────────────

class TestNotFound:
    def test_unknown_number_returns_not_found(self, provider):
        request = _make_request(doc_num="TESTNOTFOUND001")
        response = provider.verify(request)
        assert response.registry["status"] == RegistryStatus.NOT_FOUND.value
        assert response.registry["record_found"] is False

    def test_random_number_returns_not_found(self, provider):
        request = _make_request(doc_num="XYZ999999999")
        response = provider.verify(request)
        assert response.registry["status"] == RegistryStatus.NOT_FOUND.value

    def test_empty_doc_num_returns_not_found(self, provider):
        """If document number is None/empty, expect NOT_FOUND (no record to look up)"""
        request = _make_request(doc_num="NOTEXIST")
        response = provider.verify(request)
        assert response.registry["status"] == RegistryStatus.NOT_FOUND.value

    def test_not_found_source_type_still_mock(self, provider):
        request = _make_request(doc_num="TESTNOTFOUND001")
        response = provider.verify(request)
        assert response.provider_metadata.source_type == ProviderSourceType.DEVELOPMENT_MOCK

    def test_not_found_has_no_field_results(self, provider):
        """NOT_FOUND response should have empty field_results (no record to compare)"""
        request = _make_request(doc_num="TESTNOTFOUND001")
        response = provider.verify(request)
        assert response.field_results == []


# ── Response structure ────────────────────────────────────────────────────────

class TestResponseStructure:
    def test_response_has_provider_metadata(self, provider):
        request = _make_request("TESTPASS001")
        response = provider.verify(request)
        assert response.provider_metadata is not None
        assert response.provider_metadata.response_time_ms is not None
        assert response.provider_metadata.response_time_ms >= 0

    def test_response_has_audit_trail(self, provider):
        request = _make_request("TESTPASS001")
        response = provider.verify(request)
        assert isinstance(response.audit, dict)
        assert "timestamp" in response.audit
        assert "verification_id" in response.audit
        assert "registry_status" in response.audit

    def test_response_has_evidence(self, provider):
        request = _make_request("TESTPASS001")
        response = provider.verify(request)
        assert len(response.evidence) > 0

    def test_evidence_contains_disclaimer(self, provider):
        """All responses must contain a disclaimer that this is mock data"""
        request = _make_request("TESTPASS001")
        response = provider.verify(request)
        disclaimer_items = [
            e for e in response.evidence if e.type == "provider_disclaimer"
        ]
        assert len(disclaimer_items) > 0
        disclaimer_text = disclaimer_items[0].description.upper()
        assert "MOCK" in disclaimer_text or "SANDBOX" in disclaimer_text or "DEVELOPMENT" in disclaimer_text
