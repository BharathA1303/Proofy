"""
backend/tests/test_border_permit_registry.py

Integration and unit tests for Module 5: Border Permit Registry Verification.
Tests adapter translation, provider resolution, deterministic mock records,
status resolution (MATCHED, EXPIRED, REVOKED, SUSPENDED, MISMATCH),
and failure modes (TIMEOUT, UNAVAILABLE, NOT_FOUND).
"""
import pytest
from app.core.exceptions import RegistryProviderUnavailable, RegistryTimeout
from app.schemas.registry import (
    ProviderSourceType,
    RegistryStatus,
    RegistryVerificationRequest,
)
from app.services.registry.adapters.border_permit_adapter import (
    BorderPermitRegistryAdapter,
)
from app.services.registry.engine import RegistryEngine
from app.services.registry.providers.mock_border_permit import (
    MockBorderPermitRegistryProvider,
)
from app.services.registry.resolver import provider_resolver
from app.services.registry.session_store import registry_session_store


class TestBorderPermitRegistry:
    def test_adapter_builds_request(self):
        adapter = BorderPermitRegistryAdapter()
        session_data = {
            "permit_number": "BP-2026-000123",
            "name": "ALEX DUPONT",
            "date_of_birth": "1990-08-12",
            "valid_to": "2026-12-31",
            "issuing_authority": "Border Management Authority",
        }
        req = adapter.build_request("vid-bp-test-1", session_data)

        assert req.document_type == "border_permit"
        assert req.document_number.value == "BP2026000123"
        assert req.name.value == "ALEX DUPONT"
        assert req.date_of_birth.value == "1990-08-12"
        assert req.expiry_date.value == "2026-12-31"

    def test_provider_resolver_border_permit(self):
        provider = provider_resolver.resolve("border_permit")
        assert isinstance(provider, MockBorderPermitRegistryProvider)
        assert provider.provider_id == "mock_border_permit_registry"

    def test_registry_matched(self):
        adapter = BorderPermitRegistryAdapter()
        session_data = {
            "permit_number": "TESTBP001",
            "name": "ALEX DUPONT",
            "date_of_birth": "1990-08-12",
            "valid_to": "2026-12-31",
        }
        req = adapter.build_request("vid-test-matched", session_data)
        provider = MockBorderPermitRegistryProvider()
        resp = provider.verify(req)

        assert resp.registry["status"] == RegistryStatus.MATCHED.value
        assert resp.registry["record_found"] is True
        assert resp.provider_metadata.source_type == ProviderSourceType.DEVELOPMENT_MOCK

    def test_registry_synthetic_bp_matched(self):
        adapter = BorderPermitRegistryAdapter()
        session_data = {
            "permit_number": "BP2026000123",
            "name": "ALEX DUPONT",
            "date_of_birth": "1990-08-12",
            "valid_to": "2026-12-31",
        }
        req = adapter.build_request("vid-test-bp", session_data)
        provider = MockBorderPermitRegistryProvider()
        resp = provider.verify(req)

        assert resp.registry["status"] == RegistryStatus.MATCHED.value
        assert resp.registry["record_found"] is True

    def test_registry_expired(self):
        adapter = BorderPermitRegistryAdapter()
        session_data = {
            "permit_number": "TESTBPEXPIRED001",
            "name": "TEST EXPIRED",
            "date_of_birth": "1980-01-01",
            "valid_to": "2020-01-01",
        }
        req = adapter.build_request("vid-test-exp", session_data)
        provider = MockBorderPermitRegistryProvider()
        resp = provider.verify(req)

        assert resp.registry["status"] == RegistryStatus.EXPIRED.value

    def test_registry_revoked(self):
        adapter = BorderPermitRegistryAdapter()
        session_data = {
            "permit_number": "TESTBPREVOKED001",
            "name": "TEST REVOKED",
        }
        req = adapter.build_request("vid-test-rev", session_data)
        provider = MockBorderPermitRegistryProvider()
        resp = provider.verify(req)

        assert resp.registry["status"] == RegistryStatus.REVOKED.value

    def test_registry_suspended(self):
        adapter = BorderPermitRegistryAdapter()
        session_data = {
            "permit_number": "TESTBPSUSPENDED001",
            "name": "TEST SUSPENDED",
        }
        req = adapter.build_request("vid-test-susp", session_data)
        provider = MockBorderPermitRegistryProvider()
        resp = provider.verify(req)

        assert resp.registry["status"] == RegistryStatus.SUSPENDED.value

    def test_registry_mismatch(self):
        adapter = BorderPermitRegistryAdapter()
        # Different name from mock database
        session_data = {
            "permit_number": "TESTBPMISMATCH001",
            "name": "DIFFERENT NAME HERE",
        }
        req = adapter.build_request("vid-test-mis", session_data)
        provider = MockBorderPermitRegistryProvider()
        resp = provider.verify(req)

        assert resp.registry["status"] == RegistryStatus.MISMATCH.value

    def test_registry_timeout(self):
        adapter = BorderPermitRegistryAdapter()
        session_data = {"permit_number": "TESTBPTIMEOUT001"}
        req = adapter.build_request("vid-test-to", session_data)
        provider = MockBorderPermitRegistryProvider()

        with pytest.raises(RegistryTimeout):
            provider.verify(req)

    def test_registry_unavailable(self):
        adapter = BorderPermitRegistryAdapter()
        session_data = {"permit_number": "TESTBPUNAVAIL001"}
        req = adapter.build_request("vid-test-un", session_data)
        provider = MockBorderPermitRegistryProvider()

        with pytest.raises(RegistryProviderUnavailable):
            provider.verify(req)

    def test_registry_not_found(self):
        adapter = BorderPermitRegistryAdapter()
        session_data = {"permit_number": "BP9999999999"}
        req = adapter.build_request("vid-test-nf", session_data)
        provider = MockBorderPermitRegistryProvider()
        resp = provider.verify(req)

        assert resp.registry["status"] == RegistryStatus.NOT_FOUND.value
        assert resp.registry["record_found"] is False

    def test_engine_orchestration_with_session_store(self):
        vid = "vid-bp-engine-test"
        registry_session_store.set(vid, {
            "document_type": "border_permit",
            "permit_number": "BP2026000123",
            "name": "ALEX DUPONT",
            "date_of_birth": "1990-08-12",
            "valid_to": "2026-12-31",
            "issuing_authority": "Border Management Authority",
        })

        engine = RegistryEngine()
        result = engine.verify(vid, "border_permit")

        assert result.registry["status"] == "MATCHED"
        assert result.provider_metadata.source_type == ProviderSourceType.DEVELOPMENT_MOCK
