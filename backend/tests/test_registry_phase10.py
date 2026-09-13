"""
backend/tests/test_registry_phase10.py

Comprehensive Phase 10 Test Suite:
Generic Registry Intelligence & Authoritative Corroboration.

Tests:
- Mock DL Active Matched, Mismatched, Expired, Active-Doc-Expired, Revoked, Suspended, Not Found
- Normalization: DL number formatting, names, dates, COV taxonomy (match, partial, mismatch), state code/legacy
- Missing field handling (MISSING_IN_DOCUMENT, MISSING_IN_REGISTRY)
- Client Trust Boundary & Zero Client Trust (server-constructed queries)
- Mock Identification (source_type is development_mock, clear disclaimer)
- External Provider unconfigured state (LIVE_PROVIDER_NOT_CONFIGURED)
- External Provider SSRF defense (loopback, private IP, link-local, cloud metadata, allowed hosts)
- External Provider strict response schema validation (never collapses malformed payload to NOT_FOUND)
- External Provider bounded retries (transient vs permanent errors)
- Registry Cache & deduplication (preserves retrieved_at, updates freshness, clone safety)
- Non-Adjudication Principle (evidence only, never declares FORGED or AUTHENTIC)
- Evidence serialization (.to_evidence_dict())
"""
from __future__ import annotations

import copy
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.core.exceptions import (
    RegistryAuthenticationError,
    RegistryConfigurationError,
    RegistryProviderError,
    RegistryProviderUnavailable,
    RegistryResponseInvalid,
    RegistryTimeout,
)
from app.schemas.registry import (
    DocumentFieldSource,
    FieldMatchStatus,
    FieldProvenance,
    ProviderSourceType,
    RegistryRecord,
    RegistryStatus,
    RegistryVerificationRequest,
    RegistryVerificationResponse,
)
from app.services.registry.cache import RegistryCache, registry_cache
from app.services.registry.comparator import compare_fields
from app.services.registry.engine import RegistryEngine, registry_engine
from app.services.registry.normalizers import (
    license_numbers_match,
    states_match,
    vehicle_classes_match,
)
from app.services.registry.providers.external_provider import (
    AuthorizedExternalRegistryProvider,
    validate_endpoint_url,
)
from app.services.registry.providers.mock_driving_license import (
    MockDrivingLicenseRegistryProvider,
)
from app.services.registry.session_store import RegistrySessionStore, registry_session_store


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures and Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_provenance(value: str | None, source: str = "parsed") -> FieldProvenance:
    src_enum = getattr(DocumentFieldSource, source.upper(), DocumentFieldSource.PARSED)
    return FieldProvenance(value=value, source=src_enum)


def _make_dl_request(
    dl_number: str,
    name: str = "RAHUL SHARMA",
    dob: str = "1992-05-15",
    expiry: str = "2035-05-14",
    valid_from: str = "2015-05-15",
    vehicle_classes: str = "LMV, MCWG",
    state: str = "DL",
    blood_group: str = "B+",
    verification_id: str = "p10-dl-test-session",
) -> RegistryVerificationRequest:
    return RegistryVerificationRequest(
        verification_id=verification_id,
        document_type="driving_license",
        document_number=_make_provenance(dl_number),
        name=_make_provenance(name),
        date_of_birth=_make_provenance(dob),
        expiry_date=_make_provenance(expiry),
        valid_from=_make_provenance(valid_from),
        vehicle_classes=_make_provenance(vehicle_classes),
        state=_make_provenance(state),
        blood_group=_make_provenance(blood_group),
        issuing_authority=_make_provenance("RTO DELHI"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Mock Driving License Provider Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMockDrivingLicenseProvider:
    """Validate mock DL provider behaviors according to the Phase 10 specification."""

    @pytest.fixture
    def provider(self):
        p = MockDrivingLicenseRegistryProvider()
        p.initialize()
        return p

    def test_mock_dl_active_matched(self, provider):
        """Active DL matching on document_number, name, dob -> MATCHED with evidence & telemetry."""
        req = _make_dl_request("TESTDL001", name="RAHUL SHARMA", dob="1992-05-15")
        res = provider.verify(req)

        assert res.registry["status"] == RegistryStatus.MATCHED.value
        assert res.registry["record_found"] is True
        assert res.registry["registry_document_status"] == "ACTIVE"
        assert res.provider_metadata.source_type == ProviderSourceType.DEVELOPMENT_MOCK
        assert res.query_hash is not None
        assert res.freshness["is_fresh"] is True
        assert res.profile_version == "0.9.0"
        assert len(res.field_comparisons) > 0

    def test_mock_dl_active_mismatched(self, provider):
        """DL found but critical field name differs -> MISMATCH."""
        req = _make_dl_request("TESTDL001", name="VIKRAM MALHOTRA", dob="1992-05-15")
        res = provider.verify(req)

        assert res.registry["status"] == RegistryStatus.MISMATCH.value
        assert res.registry["record_found"] is True
        name_res = next((fr for fr in res.field_results if fr.field == "name"), None)
        assert name_res is not None
        assert name_res.status == FieldMatchStatus.MISMATCH

    def test_mock_dl_not_found(self, provider):
        """Unseeded document number -> NOT_FOUND, record_found=False."""
        req = _make_dl_request("NONEXISTENTDL99999")
        res = provider.verify(req)

        assert res.registry["status"] == RegistryStatus.NOT_FOUND.value
        assert res.registry["record_found"] is False

    def test_mock_dl_expired(self, provider):
        """DL marked EXPIRED in registry records -> EXPIRED status."""
        req = _make_dl_request("TESTDLEXPIRED001", name="TEST DL EXPIRED", dob="1982-04-20")
        res = provider.verify(req)

        assert res.registry["status"] == RegistryStatus.EXPIRED.value
        assert res.registry["record_found"] is True
        assert res.registry["registry_document_status"] == "EXPIRED"

    def test_mock_dl_active_but_doc_expired(self, provider):
        """Registry status is ACTIVE, but document presented has expired date -> detects renewal discrepancy."""
        # TESTDL001 is ACTIVE in registry (valid to 2035), but document presented has expiry in 2020
        req = _make_dl_request("TESTDL001", name="RAHUL SHARMA", dob="1992-05-15", expiry="2020-01-01")
        res = provider.verify(req)

        assert res.registry["record_found"] is True
        expired_ev = any(
            "expired" in e.description.lower() or e.type == "registry_active_document_expired"
            for e in res.evidence
        )
        assert expired_ev is True

    def test_mock_dl_revoked(self, provider):
        """Revoked or blacklisted DL -> REVOKED."""
        req = _make_dl_request("TESTDLREVOKED001", name="TEST REVOKED", dob="1975-06-15")
        res = provider.verify(req)

        assert res.registry["status"] == RegistryStatus.REVOKED.value
        assert res.registry["record_found"] is True

    def test_mock_dl_suspended(self, provider):
        """Suspended DL -> SUSPENDED."""
        req = _make_dl_request("TESTDLSUSPENDED001", name="TEST SUSPENDED", dob="1988-10-20")
        res = provider.verify(req)

        assert res.registry["status"] == RegistryStatus.SUSPENDED.value
        assert res.registry["record_found"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 2. Normalization & Corroboration Comparator Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRegistryCorroborationNormalization:
    """Test field normalization, COV taxonomy, state handling, and license formatting."""

    def test_dl_number_normalization_match(self):
        """License numbers match across formatting differences (spaces, hyphens, case)."""
        assert license_numbers_match("DL-04-2011-0012345", "DL04 20110012345") is True
        assert license_numbers_match("MH12 20150098765", "MH-12-2015-0098765") is True
        assert license_numbers_match("ka 01 20200001234", "KA0120200001234") is True
        assert license_numbers_match("DL0420110012345", "DL0420110099999") is False

    def test_dl_cov_matching_taxonomy(self):
        """COV taxonomy handles exact match, partial match, and complete mismatch."""
        # Full match
        status, note = vehicle_classes_match("LMV, MCWG", ["MCWG", "LMV"])
        assert status == "MATCH"

        # Partial match: document has LMV, MCWG; registry has LMV, MCWG, TRANS
        status, note = vehicle_classes_match("LMV, MCWG", "LMV, MCWG, HGMV")
        assert status == "PARTIAL_MATCH"

        # Complete mismatch: disjoint COV sets
        status, note = vehicle_classes_match("MCWG", "HGMV, TRANS")
        assert status == "MISMATCH"

        # None / empty handling
        status, note = vehicle_classes_match(None, "LMV")
        assert status == "MISSING_IN_DOCUMENT"

    def test_dl_state_code_canonical_and_legacy(self):
        """State corroboration handles 2-letter codes, names, and legacy renames."""
        # Canonical 2-letter match
        assert states_match("DL", "DL") is True
        assert states_match("MH", "Maharashtra") is True
        assert states_match("Karnataka", "KA") is True

        # Legacy state renames (OR -> OD, UA -> UK, DD/DN -> DH)
        assert states_match("OR", "OD") is True
        assert states_match("UA", "UK") is True
        assert states_match("DD", "DH") is True
        assert states_match("DN", "DH") is True

        # Mismatched states
        assert states_match("DL", "MH") is False
        assert states_match("TN", "Karnataka") is False

    def test_missing_field_handling_in_comparator(self):
        """Missing secondary fields do not cause false MISMATCH or crash."""
        req = _make_dl_request("TESTDL001", blood_group=None, valid_from=None)
        rec = RegistryRecord(
            document_number="TESTDL001",
            name="RAHUL SHARMA",
            date_of_birth="1992-05-15",
            registry_document_status="ACTIVE",
            blood_group="B+",
            valid_from="2015-05-15",
        )
        field_results, status = compare_fields(req, rec)

        assert status == RegistryStatus.MATCHED
        bg_res = next((f for f in field_results if f.field == "blood_group"), None)
        assert bg_res is not None
        assert bg_res.status == FieldMatchStatus.MISSING_IN_DOCUMENT


# ─────────────────────────────────────────────────────────────────────────────
# 3. Client Trust Boundary & Engine Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRegistryClientTrustBoundary:
    """Ensure client cannot tamper with query parameters, scores, or claims."""

    def test_client_trust_boundary_session_lookup(self):
        """Server constructs query exclusively from trusted server-side session store."""
        vid = "untrusted-client-session-10"
        # Seed server session store with genuine DL data
        registry_session_store.set(vid, {
            "document_type": "driving_license",
            "document_number": "TESTDL001",
            "name": "RAHUL SHARMA",
            "date_of_birth": "1992-05-15",
            "client_claims": {"status": "GOVERNMENT_VERIFIED", "risk_score": 0.0},
        })

        engine = RegistryEngine(cache_enabled=False)
        response = engine.verify(vid, "driving_license")

        # The query succeeded via server-side session store
        assert response.registry["status"] == RegistryStatus.MATCHED.value
        # Verification response must NOT contain any client claims or risk scores
        resp_dict = response.model_dump()
        assert "risk_score" not in resp_dict
        assert "client_claims" not in resp_dict

    def test_mock_identification_never_claims_live_authority(self):
        """Responses from mock provider must explicitly advertise DEVELOPMENT_MOCK."""
        vid = "mock-id-check-session"
        registry_session_store.set(vid, {
            "document_type": "driving_license",
            "document_number": "TESTDL001",
            "name": "RAHUL SHARMA",
            "date_of_birth": "1992-05-15",
        })

        engine = RegistryEngine(cache_enabled=False)
        response = engine.verify(vid, "driving_license")

        assert response.provider_metadata.source_type == ProviderSourceType.DEVELOPMENT_MOCK
        assert response.provider_type == ProviderSourceType.DEVELOPMENT_MOCK.value


# ─────────────────────────────────────────────────────────────────────────────
# 4. External Provider: SSRF, Schema Validation, Bounded Retries
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthorizedExternalRegistryProvider:
    """Test generic external provider security controls, SSRF defense, retries, and errors."""

    def test_unconfigured_external_provider_clean_status(self):
        """Unconfigured provider returns LIVE_PROVIDER_NOT_CONFIGURED cleanly."""
        provider = AuthorizedExternalRegistryProvider(
            provider_id="unconfigured_parivahan_api",
            endpoint_url=None,
            api_key=None,
        )
        provider.initialize()
        assert provider.is_available() is False

        req = _make_dl_request("DL0420110012345")
        res = provider.verify(req)

        assert res.registry["status"] == RegistryStatus.LIVE_PROVIDER_NOT_CONFIGURED.value
        assert res.registry["record_found"] is False
        assert res.provider_metadata.source_type == ProviderSourceType.NOT_CONFIGURED

    def test_ssrf_blocking_loopback(self):
        """SSRF: loopback 127.0.0.1 and localhost must be blocked."""
        with pytest.raises(RegistryConfigurationError, match="SSRF protection"):
            validate_endpoint_url("https://127.0.0.1/api/verify")

        with pytest.raises(RegistryConfigurationError, match="SSRF protection"):
            validate_endpoint_url("https://localhost/api/verify")

    def test_ssrf_blocking_private_ips(self):
        """SSRF: private network ranges (10.0.0.0/8, 192.168.0.0/16, 172.16.0.0/12) must be blocked."""
        with pytest.raises(RegistryConfigurationError, match="SSRF protection"):
            validate_endpoint_url("https://10.1.2.3/api/verify")

        with pytest.raises(RegistryConfigurationError, match="SSRF protection"):
            validate_endpoint_url("https://192.168.1.100/api/verify")

        with pytest.raises(RegistryConfigurationError, match="SSRF protection"):
            validate_endpoint_url("https://172.20.0.5/api/verify")

    def test_ssrf_blocking_cloud_metadata(self):
        """SSRF: AWS/GCP cloud metadata IP 169.254.169.254 must be blocked."""
        with pytest.raises(RegistryConfigurationError, match="SSRF protection"):
            validate_endpoint_url("https://169.254.169.254/latest/meta-data/")

        with pytest.raises(RegistryConfigurationError, match="SSRF protection"):
            validate_endpoint_url("https://metadata.google.internal/computeMetadata/v1/")

    def test_ssrf_allowed_hosts_enforcement(self):
        """Hostnames outside configured allowed_hosts must be rejected."""
        allowed = ["api.parivahan.gov.in", "*.nic.in"]
        # Valid host
        validate_endpoint_url("https://api.parivahan.gov.in/dl", allowed_hosts=allowed, allow_insecure_http=False)
        validate_endpoint_url("https://sarathi.nic.in/dl", allowed_hosts=allowed, allow_insecure_http=False)

        # Invalid host outside allowed domains
        with pytest.raises(RegistryConfigurationError, match="SSRF protection"):
            validate_endpoint_url("https://evil-attacker.com/dl", allowed_hosts=allowed)

    @patch("requests.post")
    def test_external_provider_schema_validation_failure(self, mock_post):
        """Malformed JSON or HTML 500 does NOT collapse to NOT_FOUND; emits PROVIDER_RESPONSE_INVALID."""
        provider = AuthorizedExternalRegistryProvider(
            provider_id="mock_ext_dl",
            endpoint_url="https://api.parivahan.gov.in/dl/verify",
            api_key="secret-token-123",
            allowed_hosts=["api.parivahan.gov.in"],
        )
        # Mock HTML error response instead of expected JSON record
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("Invalid JSON")
        mock_post.return_value = mock_resp

        req = _make_dl_request("DL0420110012345")
        with pytest.raises(RegistryResponseInvalid):
            provider.verify(req)

    @patch("requests.post")
    def test_external_provider_bounded_retries_transient(self, mock_post):
        """Transient 503 or 429 retries up to max_retries with backoff."""
        provider = AuthorizedExternalRegistryProvider(
            provider_id="mock_ext_dl",
            endpoint_url="https://api.parivahan.gov.in/dl/verify",
            api_key="secret-token-123",
            allowed_hosts=["api.parivahan.gov.in"],
            retry_policy={"max_retries": 2, "backoff_factor": 0.01, "retryable_statuses": [503]},
        )

        mock_resp_fail = MagicMock()
        mock_resp_fail.status_code = 503

        mock_resp_success = MagicMock()
        mock_resp_success.status_code = 200
        mock_resp_success.json.return_value = {
            "record": {
                "document_number": "DL0420110012345",
                "name": "RAHUL SHARMA",
                "date_of_birth": "1992-05-15",
                "status": "ACTIVE",
            }
        }
        # Fail first time with 503, succeed on retry
        mock_post.side_effect = [mock_resp_fail, mock_resp_success]

        req = _make_dl_request("DL0420110012345")
        res = provider.verify(req)

        assert res.registry["status"] == RegistryStatus.MATCHED.value
        assert mock_post.call_count == 2

    @patch("requests.post")
    def test_external_provider_no_retry_permanent_error(self, mock_post):
        """Permanent 401 Unauthorized fails immediately without retrying."""
        provider = AuthorizedExternalRegistryProvider(
            provider_id="mock_ext_dl",
            endpoint_url="https://api.parivahan.gov.in/dl/verify",
            api_key="invalid-token",
            allowed_hosts=["api.parivahan.gov.in"],
            retry_policy={"max_retries": 2, "backoff_factor": 0.01, "retryable_statuses": [503]},
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_post.return_value = mock_resp

        req = _make_dl_request("DL0420110012345")
        with pytest.raises(RegistryAuthenticationError):
            provider.verify(req)

        # Ensure only 1 outbound call was made (no retries)
        assert mock_post.call_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# 5. Registry Cache & Freshness Telemetry Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRegistryCache:
    """Validate thread-safe cache deduplication and freshness telemetry."""

    def test_cache_deduplication_and_freshness(self):
        """Repeated lookup within TTL returns cached clone with freshness metadata."""
        cache = RegistryCache(default_ttl_seconds=10.0)
        req = _make_dl_request("TESTDL001")

        provider = MockDrivingLicenseRegistryProvider()
        provider.initialize()

        res1 = provider.verify(req)
        query_hash = res1.query_hash

        # Store in cache
        cache.set("driving_license", query_hash, res1, provider.provider_id)
        assert cache.size() == 1

        # Fetch from cache
        cached_res = cache.get("driving_license", query_hash, provider.provider_id)
        assert cached_res is not None
        assert cached_res.freshness["cached"] is True
        assert cached_res.freshness["source"] == "cache"
        assert cached_res.freshness["ttl_seconds"] > 0
        assert cached_res.registry["status"] == res1.registry["status"]

    def test_cache_invalidation(self):
        """Invalidating cache removes specific entry."""
        cache = RegistryCache(default_ttl_seconds=10.0)
        cache.set("driving_license", "hash123", MagicMock(registry={"status": "MATCHED"}), "provider_a")
        assert cache.size() == 1

        removed = cache.invalidate("driving_license", "hash123", "provider_a")
        assert removed is True
        assert cache.get("driving_license", "hash123", "provider_a") is None

    def test_engine_returns_cached_response(self):
        """Engine automatically deduplicates repeated calls via internal cache."""
        engine = RegistryEngine(cache_enabled=True)
        engine.cache.clear()

        vid1 = "cache-test-session-1"
        vid2 = "cache-test-session-2"
        registry_session_store.set(vid1, {
            "document_type": "driving_license",
            "document_number": "TESTDL001",
            "name": "RAHUL SHARMA",
            "date_of_birth": "1992-05-15",
        })
        registry_session_store.set(vid2, {
            "document_type": "driving_license",
            "document_number": "TESTDL001",
            "name": "RAHUL SHARMA",
            "date_of_birth": "1992-05-15",
        })

        res1 = engine.verify(vid1, "driving_license")
        assert res1.freshness.get("cached") is not True

        res2 = engine.verify(vid2, "driving_license")
        assert res2.freshness.get("cached") is True
        assert res2.verification_id == vid2
        assert res2.audit["verification_id"] == vid2


# ─────────────────────────────────────────────────────────────────────────────
# 6. Non-Adjudication Principle & Evidence Serialization
# ─────────────────────────────────────────────────────────────────────────────

class TestNonAdjudicationAndEvidenceSerialization:
    """Verify Non-Adjudication Principle and structured evidence serialization."""

    def test_non_adjudication_principle(self):
        """Registry verification responses must NEVER contain risk verdicts or final decisions."""
        provider = MockDrivingLicenseRegistryProvider()
        provider.initialize()

        req = _make_dl_request("TESTDLREVOKED001")
        res = provider.verify(req)
        dump = res.model_dump()

        # Forbidden adjudication vocabulary
        for forbidden in ("risk_score", "final_decision", "verdict", "FORGED", "AUTHENTIC", "CLEARED", "DENIED"):
            assert forbidden not in dump
            assert forbidden.lower() not in dump

    def test_to_evidence_dict_serialization(self):
        """to_evidence_dict() produces valid structured dict for Risk Engine and audit log."""
        provider = MockDrivingLicenseRegistryProvider()
        provider.initialize()

        req = _make_dl_request("TESTDL001")
        res = provider.verify(req)

        evidence_dict = res.to_evidence_dict()
        assert isinstance(evidence_dict, dict)
        assert evidence_dict["verification_id"] == "p10-dl-test-session"
        assert evidence_dict["document_type"] == "driving_license"
        assert evidence_dict["lookup_status"] == RegistryStatus.MATCHED.value
        assert evidence_dict["record_found"] is True
        assert evidence_dict["query_hash"] is not None
        assert isinstance(evidence_dict["field_results"], list)
        assert isinstance(evidence_dict["evidence"], list)
        assert evidence_dict["profile_version"] == "0.9.0"
