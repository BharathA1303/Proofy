"""
backend/tests/test_national_id_registry.py

Tests for Module 5 National ID Registry Verification:
- NationalIdRegistryAdapter
- MockNationalIdRegistryProvider
- Deterministic status outcomes: MATCHED, EXPIRED, REVOKED, SUSPENDED, MISMATCH, TIMEOUT, UNAVAILABLE, NOT_FOUND
- Transparent development mock source visibility
- Sensitive identifier masking in evidence
"""
import pytest
from app.core.exceptions import RegistryProviderUnavailable, RegistryTimeout
from app.schemas.registry import (
    ProviderSourceType,
    RegistryStatus,
    RegistryVerificationRequest,
)
from app.services.registry.adapters.national_id_adapter import (
    NationalIdRegistryAdapter,
)
from app.services.registry.engine import registry_engine
from app.services.registry.providers.mock_national_id import (
    MockNationalIdRegistryProvider,
)
from app.services.registry.resolver import provider_resolver
from app.services.registry.session_store import registry_session_store


class TestNationalIdRegistry:
    def test_adapter_builds_request(self):
        adapter = NationalIdRegistryAdapter()
        session_data = {
            "identity_number": "9876 5432 1098",
            "name": "Rahul Sharma",
            "date_of_birth": "1992-05-15",
            "issuing_authority": "UIDAI",
        }
        req = adapter.build_request("vid-test-01", session_data)

        assert req.verification_id == "vid-test-01"
        assert req.document_type == "national_id"
        assert req.document_number.value == "987654321098"
        assert req.name.value == "RAHUL SHARMA"
        assert req.date_of_birth.value == "1992-05-15"
        assert req.expiry_date is None

    def test_provider_resolver_national_id(self):
        provider = provider_resolver.resolve("national_id")
        assert isinstance(provider, MockNationalIdRegistryProvider)
        assert provider.supports("national_id") is True

    def test_registry_matched(self):
        provider = MockNationalIdRegistryProvider()
        adapter = NationalIdRegistryAdapter()

        session_data = {
            "identity_number": "TESTNID001",
            "name": "RAHUL SHARMA",
            "date_of_birth": "1992-05-15",
        }
        req = adapter.build_request("vid-test-matched", session_data)
        resp = provider.verify(req)

        assert resp.registry["status"] == RegistryStatus.MATCHED.value
        assert resp.registry["record_found"] is True
        assert resp.provider_metadata.source_type == ProviderSourceType.DEVELOPMENT_MOCK

    def test_registry_synthetic_12digit_matched(self):
        provider = MockNationalIdRegistryProvider()
        adapter = NationalIdRegistryAdapter()

        session_data = {
            "identity_number": "987654321098",
            "name": "RAHUL SHARMA",
            "date_of_birth": "1992-05-15",
        }
        req = adapter.build_request("vid-test-12digit", session_data)
        resp = provider.verify(req)

        assert resp.registry["status"] == RegistryStatus.MATCHED.value
        assert resp.registry["record_found"] is True

    def test_registry_expired(self):
        provider = MockNationalIdRegistryProvider()
        adapter = NationalIdRegistryAdapter()

        session_data = {
            "identity_number": "TESTNIDEXPIRED001",
            "name": "TEST EXPIRED",
            "date_of_birth": "1980-01-01",
        }
        req = adapter.build_request("vid-test-exp", session_data)
        resp = provider.verify(req)

        assert resp.registry["status"] == RegistryStatus.EXPIRED.value

    def test_registry_revoked(self):
        provider = MockNationalIdRegistryProvider()
        adapter = NationalIdRegistryAdapter()

        session_data = {
            "identity_number": "TESTNIDREVOKED001",
            "name": "TEST REVOKED",
            "date_of_birth": "1975-06-15",
        }
        req = adapter.build_request("vid-test-rev", session_data)
        resp = provider.verify(req)

        assert resp.registry["status"] == RegistryStatus.REVOKED.value

    def test_registry_suspended(self):
        provider = MockNationalIdRegistryProvider()
        adapter = NationalIdRegistryAdapter()

        session_data = {
            "identity_number": "TESTNIDSUSPENDED001",
            "name": "TEST SUSPENDED",
            "date_of_birth": "1988-10-20",
        }
        req = adapter.build_request("vid-test-susp", session_data)
        resp = provider.verify(req)

        assert resp.registry["status"] == RegistryStatus.SUSPENDED.value

    def test_registry_mismatch(self):
        provider = MockNationalIdRegistryProvider()
        adapter = NationalIdRegistryAdapter()

        session_data = {
            "identity_number": "TESTNIDMISMATCH001",
            "name": "DIFFERENT PERSON",  # Record in DB is VIKRAM SINGH
            "date_of_birth": "1965-03-12",
        }
        req = adapter.build_request("vid-test-mis", session_data)
        resp = provider.verify(req)

        assert resp.registry["status"] == RegistryStatus.MISMATCH.value

    def test_registry_timeout(self):
        provider = MockNationalIdRegistryProvider()
        adapter = NationalIdRegistryAdapter()

        session_data = {"identity_number": "TESTNIDTIMEOUT001"}
        req = adapter.build_request("vid-test-to", session_data)
        with pytest.raises(RegistryTimeout):
            provider.verify(req)

    def test_registry_unavailable(self):
        provider = MockNationalIdRegistryProvider()
        adapter = NationalIdRegistryAdapter()

        session_data = {"identity_number": "TESTNIDUNAVAIL001"}
        req = adapter.build_request("vid-test-un", session_data)
        with pytest.raises(RegistryProviderUnavailable):
            provider.verify(req)

    def test_registry_not_found(self):
        provider = MockNationalIdRegistryProvider()
        adapter = NationalIdRegistryAdapter()

        session_data = {"identity_number": "UNKNOWN_ID_9999"}
        req = adapter.build_request("vid-test-nf", session_data)
        resp = provider.verify(req)

        assert resp.registry["status"] == RegistryStatus.NOT_FOUND.value
        assert resp.registry["record_found"] is False

    def test_engine_orchestration_with_session_store(self):
        vid = "vid-nid-engine-test"
        registry_session_store.set(vid, {
            "document_type": "national_id",
            "identity_number": "TESTNID001",
            "name": "RAHUL SHARMA",
            "date_of_birth": "1992-05-15",
        })

        resp = registry_engine.verify(vid, "national_id")
        assert resp.registry["status"] == RegistryStatus.MATCHED.value
        assert resp.provider_metadata.source_type == ProviderSourceType.DEVELOPMENT_MOCK
