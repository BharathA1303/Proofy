"""
backend/tests/test_dl_registry.py

Unit tests for Driving License Registry Adapter and Mock Registry Provider.
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
from app.services.registry.adapters.driving_license_adapter import DrivingLicenseRegistryAdapter
from app.services.registry.engine import registry_engine
from app.services.registry.providers.mock_driving_license import MockDrivingLicenseRegistryProvider
from app.services.registry.session_store import registry_session_store


def _make_dl_request(
    doc_num: str,
    name: str = "RAHUL SHARMA",
    dob: str = "1992-05-15",
    verification_id: str = "vid-dl-1",
) -> RegistryVerificationRequest:
    def p(val, src=DocumentFieldSource.VIZ):
        return FieldProvenance(value=val, source=src) if val else None

    return RegistryVerificationRequest(
        verification_id=verification_id,
        document_type="driving_license",
        document_number=p(doc_num),
        name=p(name),
        date_of_birth=p(dob),
        expiry_date=p("2035-05-14"),
        issuing_authority=p("RTO DELHI"),
    )


class TestDrivingLicenseRegistryAdapter:
    def test_build_request_from_session_data(self):
        adapter = DrivingLicenseRegistryAdapter()
        session_data = {
            "document_number": "DL0420110012345",
            "document_number_source": "viz",
            "name": "RAHUL SHARMA",
            "name_source": "viz",
            "date_of_birth": "1992-05-15",
            "dob_source": "viz",
            "expiry_date": "2035-05-14",
            "expiry_source": "viz",
            "issuing_authority": "RTO DELHI",
        }

        req = adapter.build_request("vid-test-dl-1", session_data)
        assert req.verification_id == "vid-test-dl-1"
        assert req.document_type == "driving_license"
        assert req.document_number.value == "DL0420110012345"
        assert req.name.value == "RAHUL SHARMA"
        assert req.date_of_birth.value == "1992-05-15"
        assert req.expiry_date.value == "2035-05-14"
        assert req.issuing_authority.value == "RTO DELHI"


class TestMockDrivingLicenseRegistryProvider:
    @pytest.fixture
    def provider(self):
        p = MockDrivingLicenseRegistryProvider()
        p.initialize()
        return p

    def test_provider_metadata_identifies_mock(self, provider):
        status = provider.health_check()
        assert status.source_type == ProviderSourceType.DEVELOPMENT_MOCK
        assert "driving_license" in status.supported_document_types

    def test_active_dl_matched(self, provider):
        req = _make_dl_request("TESTDL001", name="RAHUL SHARMA", dob="1992-05-15")
        res = provider.verify(req)
        assert res.registry["status"] == RegistryStatus.MATCHED.value
        assert res.registry["record_found"] is True
        assert res.provider_metadata.source_type == ProviderSourceType.DEVELOPMENT_MOCK

    def test_expired_dl_record(self, provider):
        req = _make_dl_request("TESTDLEXPIRED001", name="TEST EXPIRED", dob="1980-01-01")
        res = provider.verify(req)
        assert res.registry["status"] == RegistryStatus.EXPIRED.value

    def test_revoked_dl_record(self, provider):
        req = _make_dl_request("TESTDLREVOKED001", name="TEST REVOKED", dob="1975-06-15")
        res = provider.verify(req)
        assert res.registry["status"] == RegistryStatus.REVOKED.value

    def test_suspended_dl_record(self, provider):
        req = _make_dl_request("TESTDLSUSPENDED001", name="TEST SUSPENDED", dob="1988-10-20")
        res = provider.verify(req)
        assert res.registry["status"] == RegistryStatus.SUSPENDED.value

    def test_mismatch_dl_record(self, provider):
        req = _make_dl_request("TESTDLMISMATCH001", name="DIFFERENT PERSON", dob="1995-01-01")
        res = provider.verify(req)
        assert res.registry["status"] == RegistryStatus.MISMATCH.value

    def test_unknown_dl_not_found(self, provider):
        req = _make_dl_request("UNKNOWN_DL_12345")
        res = provider.verify(req)
        assert res.registry["status"] == RegistryStatus.NOT_FOUND.value
        assert res.registry["record_found"] is False

    def test_timeout_and_unavailable(self, provider):
        req_timeout = _make_dl_request("TESTDLTIMEOUT001")
        with pytest.raises(RegistryTimeout):
            provider.verify(req_timeout)

        req_unavail = _make_dl_request("TESTDLUNAVAIL001")
        with pytest.raises(RegistryProviderUnavailable):
            provider.verify(req_unavail)


class TestRegistryEngineDLIntegration:
    def test_engine_verifies_dl_matched(self):
        vid = "test-dl-session-001"
        registry_session_store.set(vid, {
            "document_type": "driving_license",
            "document_number": "TESTDL001",
            "name": "RAHUL SHARMA",
            "date_of_birth": "1992-05-15",
            "expiry_date": "2035-05-14",
            "issuing_authority": "RTO DELHI",
        })

        res = registry_engine.verify(vid, "driving_license")
        assert res.registry["status"] == RegistryStatus.MATCHED.value
        assert res.registry["record_found"] is True
        assert res.document_type == "driving_license"
