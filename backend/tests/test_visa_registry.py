"""
tests/test_visa_registry.py

Tests for Visa Registry verification:
- VisaRegistryAdapter session mapping
- MockVisaRegistryProvider deterministic mock records:
  TESTVISA001 (ACTIVE), TESTVISAEXPIRED001 (EXPIRED), TESTVISAREVOKED001 (REVOKED),
  TESTVISAMISMATCH001 (MISMATCH), TESTVISASUSPENDED001 (SUSPENDED),
  TESTVISATIMEOUT001 (TIMEOUT), TESTVISAUNAVAIL001 (UNAVAILABLE),
  and NOT_FOUND for unknown visa numbers.
- Verification that source_type="development_mock" is always identified.
- Generic RegistryEngine handling Visa.
"""
import pytest
from app.core.exceptions import RegistryProviderUnavailable, RegistryTimeout
from app.schemas.registry import (
    DocumentFieldSource,
    FieldProvenance,
    ProviderSourceType,
    RegistryStatus,
    RegistryVerificationRequest,
)
from app.services.registry.adapters.visa_adapter import VisaRegistryAdapter
from app.services.registry.engine import registry_engine
from app.services.registry.providers.mock_visa import MockVisaRegistryProvider
from app.services.registry.session_store import registry_session_store


def _make_visa_request(
    doc_num: str,
    name: str = "SARAH CONNOR",
    dob: str = "1985-05-12",
    nationality: str = "USA",
    verification_id: str = "test-visa-session-001",
) -> RegistryVerificationRequest:
    def p(val, src=DocumentFieldSource.VIZ):
        return FieldProvenance(value=val, source=src) if val else None

    return RegistryVerificationRequest(
        verification_id=verification_id,
        document_type="visa",
        document_number=p(doc_num),
        name=p(name),
        date_of_birth=p(dob),
        nationality=p(nationality),
        expiry_date=p("2033-01-15"),
    )


class TestVisaRegistryAdapter:
    def test_adapter_maps_visa_fields(self):
        adapter = VisaRegistryAdapter()
        session_data = {
            "document_type": "visa",
            "document_number": "TESTVISA001",
            "document_number_source": "viz",
            "name": "ALICE SMITH",
            "name_source": "viz",
            "passport_number": "P12345678",
            "passport_number_source": "viz",
            "date_of_birth": "1990-01-01",
            "dob_source": "viz",
            "nationality": "USA",
            "nationality_source": "viz",
            "visa_type": "B1/B2",
            "issue_date": "2022-01-01",
            "expiry_date": "2032-01-01",
            "expiry_source": "viz",
            "issuing_authority": "US EMBASSY",
            "authority_source": "viz",
        }
        req = adapter.build_request("test-v-123", session_data)
        assert req.document_type == "visa"
        assert req.document_number.value == "TESTVISA001"
        assert req.name.value == "ALICE SMITH"
        assert req.date_of_birth.value == "1990-01-01"
        assert req.nationality.value == "USA"
        assert req.expiry_date.value == "2032-01-01"
        assert req.issuing_authority.value == "US EMBASSY"
        assert req.document_number.source == DocumentFieldSource.VIZ


class TestMockVisaRegistryProvider:
    @pytest.fixture
    def provider(self):
        p = MockVisaRegistryProvider()
        p.initialize()
        return p

    def test_provider_metadata_identifies_mock(self, provider):
        status = provider.health_check()
        assert status.source_type == ProviderSourceType.DEVELOPMENT_MOCK
        assert "visa" in status.supported_document_types

    def test_active_visa_matched(self, provider):
        req = _make_visa_request("TESTVISA001")
        resp = provider.verify(req)
        assert resp.registry["status"] == RegistryStatus.MATCHED.value
        assert resp.registry["record_found"] is True

    def test_expired_visa_record(self, provider):
        req = _make_visa_request("TESTVISAEXPIRED001")
        resp = provider.verify(req)
        assert resp.registry["status"] == RegistryStatus.EXPIRED.value

    def test_revoked_visa_record(self, provider):
        req = _make_visa_request("TESTVISAREVOKED001")
        resp = provider.verify(req)
        assert resp.registry["status"] == RegistryStatus.REVOKED.value

    def test_mismatch_visa_record(self, provider):
        req = _make_visa_request("TESTVISAMISMATCH001", name="INTENDED MISMATCH")
        resp = provider.verify(req)
        assert resp.registry["status"] == RegistryStatus.MISMATCH.value

    def test_suspended_visa_record(self, provider):
        req = _make_visa_request("TESTVISASUSPENDED001")
        resp = provider.verify(req)
        assert resp.registry["status"] == RegistryStatus.SUSPENDED.value

    def test_unknown_visa_returns_not_found(self, provider):
        req = _make_visa_request("UNKNOWN_VISA_NUMBER_999")
        resp = provider.verify(req)
        assert resp.registry["status"] == RegistryStatus.NOT_FOUND.value
        assert resp.registry["record_found"] is False

    def test_simulated_timeout(self, provider):
        req = _make_visa_request("TESTVISATIMEOUT001")
        with pytest.raises(RegistryTimeout):
            provider.verify(req)

    def test_simulated_unavailable(self, provider):
        req = _make_visa_request("TESTVISAUNAVAIL001")
        with pytest.raises(RegistryProviderUnavailable):
            provider.verify(req)


class TestRegistryEngineVisaIntegration:
    def test_registry_engine_verifies_visa_matched(self):
        session_id = "test-visa-session-001"
        registry_session_store.set(session_id, {
            "document_type": "visa",
            "document_number": "TESTVISA001",
            "name": "SARAH CONNOR",
            "passport_number": "P9876543",
            "date_of_birth": "1985-05-12",
            "nationality": "USA",
            "visa_type": "B1/B2",
            "expiry_date": "2033-01-15",
            "issuing_authority": "EMBASSY LONDON",
        })

        resp = registry_engine.verify(session_id, "visa")
        assert resp.registry["status"] == "MATCHED"
        assert resp.provider_metadata.source_type == ProviderSourceType.DEVELOPMENT_MOCK
        assert resp.field_results is not None
        assert any(fr.field == "document_number" and fr.status == "MATCH" for fr in resp.field_results)

    def test_registry_engine_verifies_visa_not_found(self):
        session_id = "test-visa-session-notfound"
        registry_session_store.set(session_id, {
            "document_type": "visa",
            "document_number": "NOTREALVISA999",
        })

        resp = registry_engine.verify(session_id, "visa")
        assert resp.registry["status"] == "NOT_FOUND"
