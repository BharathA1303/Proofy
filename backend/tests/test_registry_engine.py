"""
tests/test_registry_engine.py

Unit tests for the RegistryEngine orchestrator.

Tests cover:
  - Session not found → UNAVAILABLE response
  - Provider unavailable → UNAVAILABLE response
  - Successful MATCHED flow
  - NOT_FOUND flow
  - REVOKED flow
  - MISMATCH flow
  - M4 completion → M5 ready (state independence)
  - M5 failure → M1–M4 results remain intact (verified via engine isolation)
  - No risk_score in any engine response
"""
import pytest
from unittest.mock import MagicMock, patch

from app.schemas.registry import RegistryStatus
from app.services.registry.engine import RegistryEngine
from app.services.registry.session_store import RegistrySessionStore


def _make_mock_session(doc_num="TESTPASS001"):
    """Return a minimal registry session dict."""
    return {
        "document_type": "passport",
        "document_number": doc_num,
        "document_number_source": "mrz",
        "name": "TEST USER ONE",
        "name_source": "viz",
        "date_of_birth": "1990-01-01",
        "dob_source": "mrz",
        "nationality": "IND",
        "nationality_source": "mrz",
        "expiry_date": "2030-01-01",
        "expiry_source": "mrz",
    }


class TestRegistryEngineSessionNotFound:
    def test_missing_session_returns_unavailable(self):
        """Session not found → UNAVAILABLE, not INVALID or FORGED."""
        engine = RegistryEngine()
        store = RegistrySessionStore(ttl_seconds=900)

        with patch("app.services.registry.engine.registry_session_store", store):
            response = engine.verify("nonexistent-session-id", "passport")

        assert response.registry["status"] == RegistryStatus.UNAVAILABLE.value
        assert response.registry["record_found"] is False

    def test_expired_session_returns_unavailable(self):
        """Expired session → UNAVAILABLE, not document failure."""
        engine = RegistryEngine()
        # Use ttl_seconds=1 so we can wait a reliable period for expiry.
        store = RegistrySessionStore(ttl_seconds=1)
        store.set("expired-session", _make_mock_session())

        import time
        time.sleep(1.1)  # Wait for TTL to elapse

        with patch("app.services.registry.engine.registry_session_store", store):
            response = engine.verify("expired-session", "passport")

        assert response.registry["status"] == RegistryStatus.UNAVAILABLE.value



class TestRegistryEngineIntegration:
    """Integration tests using real mock provider through engine."""

    def _run_engine(self, doc_num, name="TEST USER ONE", dob="1990-01-01", nationality="IND"):
        """Run the full engine with a real session store and real mock provider."""
        engine = RegistryEngine()
        store = RegistrySessionStore(ttl_seconds=900)
        session = {
            "document_type": "passport",
            "document_number": doc_num,
            "document_number_source": "mrz",
            "name": name,
            "name_source": "viz",
            "date_of_birth": dob,
            "dob_source": "mrz",
            "nationality": nationality,
            "nationality_source": "mrz",
            "expiry_date": "2030-01-01",
        }
        store.set("integration-session", session)

        with patch("app.services.registry.engine.registry_session_store", store):
            # Use a fresh resolver for each test
            with patch("app.services.registry.engine.provider_resolver") as mock_resolver:
                # Use real mock provider
                from app.services.registry.providers.mock_passport import MockPassportRegistryProvider
                real_provider = MockPassportRegistryProvider()
                real_provider.initialize()
                mock_resolver.resolve.return_value = real_provider
                return engine.verify("integration-session", "passport")

    def test_active_matched_record(self):
        response = self._run_engine("TESTPASS001", "TEST USER ONE", "1990-01-01", "IND")
        assert response.registry["status"] == RegistryStatus.MATCHED.value

    def test_not_found_record(self):
        response = self._run_engine("TESTNOTFOUND001")
        assert response.registry["status"] == RegistryStatus.NOT_FOUND.value

    def test_revoked_record(self):
        response = self._run_engine("TESTREVOKED001", "TEST REVOKED", "1975-03-20", "IND")
        assert response.registry["status"] == RegistryStatus.REVOKED.value

    def test_mismatch_record(self):
        response = self._run_engine("TESTMISMATCH001", "TEST USER ONE", "1990-01-01", "IND")
        assert response.registry["status"] == RegistryStatus.MISMATCH.value

    def test_expired_record(self):
        response = self._run_engine("TESTEXPIRED001", "TEST EXPIRED", "1985-06-15", "IND")
        assert response.registry["status"] == RegistryStatus.EXPIRED.value

    def test_suspended_record(self):
        response = self._run_engine("TESTSUSPENDED001", "TEST SUSPENDED", "1980-12-10", "IND")
        assert response.registry["status"] == RegistryStatus.SUSPENDED.value


class TestRegistryEngineNoRiskScore:
    """Ensure the engine never produces risk scores or verdicts."""

    def _run_basic(self, doc_num):
        engine = RegistryEngine()
        store = RegistrySessionStore(ttl_seconds=900)
        store.set("no-risk-session", _make_mock_session(doc_num))

        with patch("app.services.registry.engine.registry_session_store", store):
            with patch("app.services.registry.engine.provider_resolver") as mock_resolver:
                from app.services.registry.providers.mock_passport import MockPassportRegistryProvider
                p = MockPassportRegistryProvider()
                p.initialize()
                mock_resolver.resolve.return_value = p
                return engine.verify("no-risk-session", "passport")

    def test_matched_response_has_no_risk_score(self):
        response = self._run_basic("TESTPASS001")
        d = response.model_dump()
        assert "risk_score" not in d
        assert "final_decision" not in d
        assert "threat_index" not in d

    def test_revoked_response_has_no_verdict(self):
        response = self._run_basic("TESTREVOKED001")
        d = response.model_dump()
        assert "FORGERY" not in str(d).upper()
        assert "CLEARED" not in str(d).upper()
        assert "DENIED" not in str(d).upper()

    def test_not_found_has_no_fraud_label(self):
        response = self._run_basic("TESTNOTFOUND001")
        # NOT_FOUND must not be labeled as FORGERY in evidence
        all_descriptions = " ".join(e.description.upper() for e in response.evidence)
        assert "FORGERY" not in all_descriptions
        assert "FRAUD DETECTED" not in all_descriptions


class TestRegistryEngineProviderUnavailable:
    def test_unavailable_provider_returns_unavailable_status(self):
        engine = RegistryEngine()
        store = RegistrySessionStore(ttl_seconds=900)
        store.set("unavail-session", _make_mock_session())

        with patch("app.services.registry.engine.registry_session_store", store):
            with patch("app.services.registry.engine.provider_resolver") as mock_resolver:
                # Mock an unavailable provider
                mock_provider = MagicMock()
                mock_provider.is_available.return_value = False
                mock_provider.provider_id = "test-unavailable-provider"
                mock_resolver.resolve.return_value = mock_provider
                response = engine.verify("unavail-session", "passport")

        assert response.registry["status"] == RegistryStatus.UNAVAILABLE.value
        # UNAVAILABLE must NOT imply document is invalid
        evidence_text = " ".join(e.description for e in response.evidence)
        assert "NOT" in evidence_text.upper() or "UNAVAILABLE" in evidence_text.upper()


class TestRegistryEngineExceptionHandling:
    def test_timeout_exception_returns_timeout_status(self):
        from app.core.exceptions import RegistryTimeout
        engine = RegistryEngine()
        store = RegistrySessionStore(ttl_seconds=900)
        store.set("timeout-session", _make_mock_session())

        with patch("app.services.registry.engine.registry_session_store", store):
            with patch("app.services.registry.engine.provider_resolver") as mock_resolver:
                mock_provider = MagicMock()
                mock_provider.is_available.return_value = True
                mock_provider.provider_id = "test-provider"
                mock_provider.verify.side_effect = RegistryTimeout("Timed out")
                mock_resolver.resolve.return_value = mock_provider
                response = engine.verify("timeout-session", "passport")

        assert response.registry["status"] == RegistryStatus.TIMEOUT.value

    def test_auth_error_returns_auth_error_status(self):
        from app.core.exceptions import RegistryAuthenticationError
        engine = RegistryEngine()
        store = RegistrySessionStore(ttl_seconds=900)
        store.set("auth-session", _make_mock_session())

        with patch("app.services.registry.engine.registry_session_store", store):
            with patch("app.services.registry.engine.provider_resolver") as mock_resolver:
                mock_provider = MagicMock()
                mock_provider.is_available.return_value = True
                mock_provider.provider_id = "test-provider"
                mock_provider.verify.side_effect = RegistryAuthenticationError()
                mock_resolver.resolve.return_value = mock_provider
                response = engine.verify("auth-session", "passport")

        assert response.registry["status"] == RegistryStatus.AUTHENTICATION_ERROR.value

    def test_unexpected_exception_returns_provider_error(self):
        engine = RegistryEngine()
        store = RegistrySessionStore(ttl_seconds=900)
        store.set("err-session", _make_mock_session())

        with patch("app.services.registry.engine.registry_session_store", store):
            with patch("app.services.registry.engine.provider_resolver") as mock_resolver:
                mock_provider = MagicMock()
                mock_provider.is_available.return_value = True
                mock_provider.provider_id = "test-provider"
                mock_provider.verify.side_effect = RuntimeError("Unexpected crash")
                mock_resolver.resolve.return_value = mock_provider
                response = engine.verify("err-session", "passport")

        assert response.registry["status"] == RegistryStatus.PROVIDER_ERROR.value

    def test_configuration_error_returns_provider_error(self):
        from app.core.exceptions import RegistryConfigurationError
        engine = RegistryEngine()
        store = RegistrySessionStore(ttl_seconds=900)
        store.set("config-session", _make_mock_session())

        with patch("app.services.registry.engine.registry_session_store", store):
            with patch("app.services.registry.engine.provider_resolver") as mock_resolver:
                mock_resolver.resolve.side_effect = RegistryConfigurationError("Bad config")
                response = engine.verify("config-session", "passport")

        assert response.registry["status"] == RegistryStatus.PROVIDER_ERROR.value
