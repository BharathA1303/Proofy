"""
backend/app/services/registry/engine.py

Registry Verification Engine — Module 5 core orchestrator.

RESPONSIBILITIES:
  1. Receive verification_id + document_type from the API layer.
  2. Retrieve normalized session data from RegistrySessionStore.
  3. Resolve the appropriate registry provider via ProviderResolver.
  4. Select the appropriate adapter for the document type.
  5. Build the normalized RegistryVerificationRequest.
  6. Call the provider's verify() method.
  7. Handle all exception categories cleanly.
  8. Return a structured RegistryVerificationResponse.

NON-RESPONSIBILITIES (by design):
  - Calculating risk_score or final_decision
  - Interpreting REVOKED/MISMATCH as "FORGERY CONFIRMED"
  - Any face/biometric logic (belongs to Module 4)
  - Any OCR logic (belongs to Module 1)
  - Any document validation logic (belongs to Module 2)

SESSION ISOLATION:
  The engine always verifies that the session data belongs to the
  exact verification_id supplied. It never cross-contaminates sessions.

ARCHITECTURE NOTE:
  The engine does not know implementation details of providers.
  All communication goes through the RegistryProvider interface.
"""
from __future__ import annotations

import datetime
import hashlib
import logging
import time
from typing import Optional

from app.core.exceptions import (
    RegistryAuthenticationError,
    RegistryConfigurationError,
    RegistryProviderError,
    RegistryProviderUnavailable,
    RegistryResponseInvalid,
    RegistryTimeout,
)
from app.schemas.registry import (
    ProviderSourceType,
    RegistryEvidence,
    RegistryProviderMetadata,
    RegistryStatus,
    RegistryVerificationResponse,
)
from app.services.registry.adapters.passport_adapter import PassportRegistryAdapter
from app.services.registry.adapters.visa_adapter import VisaRegistryAdapter
from app.services.registry.cache import registry_cache
from app.services.registry.resolver import provider_resolver
from app.services.registry.session_store import registry_session_store

logger = logging.getLogger(__name__)

# ── Adapter registry ──────────────────────────────────────────────────────────

def _get_adapter(document_type: str):
    """Return the appropriate adapter for the document type."""
    norm = document_type.lower() if document_type else "passport"
    if norm in ("passport",):
        return PassportRegistryAdapter()
    if norm in ("visa",):
        return VisaRegistryAdapter()
    if norm in ("driving_license", "drivinglicense"):
        from app.services.registry.adapters.driving_license_adapter import (
            DrivingLicenseRegistryAdapter,
        )
        return DrivingLicenseRegistryAdapter()
    if norm in ("national_id", "nationalid", "nid", "aadhaar", "aadhaarcard", "uid"):
        # Use Aadhaar adapter (renamed from national_id_adapter; same shape)
        from app.services.registry.adapters.national_id_adapter import (
            NationalIdRegistryAdapter,
        )
        return NationalIdRegistryAdapter()
    if norm in ("voter_id", "voterid", "epic", "voter"):
        # Voter ID uses the same adapter shape as Aadhaar (generic field set)
        from app.services.registry.adapters.national_id_adapter import (
            NationalIdRegistryAdapter,
        )
        return NationalIdRegistryAdapter()
    if norm in ("pan_card", "pancard", "pan"):
        # PAN Card uses the same adapter shape (no DOB mandatory)
        from app.services.registry.adapters.national_id_adapter import (
            NationalIdRegistryAdapter,
        )
        return NationalIdRegistryAdapter()
    if norm in ("border_permit", "borderpermit"):
        from app.services.registry.adapters.border_permit_adapter import (
            BorderPermitRegistryAdapter,
        )
        return BorderPermitRegistryAdapter()
    return PassportRegistryAdapter()  # Fallback to passport adapter shape for stubs


# ── Engine ────────────────────────────────────────────────────────────────────

class RegistryEngine:
    """
    Generic Registry Verification Engine.

    Entry point: verify(verification_id, document_type)

    The engine is intentionally thin — it orchestrates, delegates, and
    handles errors. It contains no registry data, no document parsing,
    and no risk scoring.
    """

    def __init__(self, cache_enabled: bool = True) -> None:
        self.cache_enabled = cache_enabled
        self.cache = registry_cache

    def verify(
        self,
        verification_id: str,
        document_type: str,
    ) -> RegistryVerificationResponse:
        """
        Execute registry verification for a verification session.

        Args:
            verification_id: Session ID from Module 1 /ocr.
            document_type:   'passport' | 'visa' | 'driving_license' | etc.

        Returns:
            RegistryVerificationResponse with evidence, field results,
            provider metadata, and audit trail.
            NEVER returns risk scores or final decisions.
        """
        t_start = time.perf_counter()
        logger.info(
            "RegistryEngine: starting verification id=%s doc_type=%s",
            verification_id, document_type,
        )

        # ── Step 1: Retrieve session data ─────────────────────────────────
        session_data = registry_session_store.get(verification_id)

        if session_data is None:
            logger.warning(
                "RegistryEngine: session not found or expired for id=%s",
                verification_id,
            )
            return self._build_error_response(
                verification_id=verification_id,
                document_type=document_type,
                registry_status=RegistryStatus.UNAVAILABLE,
                error_description=(
                    "Verification session not found or expired. "
                    "Please restart the verification process."
                ),
                elapsed_ms=(time.perf_counter() - t_start) * 1000,
            )

        # ── Step 2: Resolve provider ──────────────────────────────────────
        try:
            provider = provider_resolver.resolve(document_type)
        except RegistryConfigurationError as exc:
            logger.error(
                "RegistryEngine: configuration error for id=%s: %s",
                verification_id, exc,
            )
            return self._build_error_response(
                verification_id=verification_id,
                document_type=document_type,
                registry_status=RegistryStatus.PROVIDER_ERROR,
                error_description=str(exc),
                elapsed_ms=(time.perf_counter() - t_start) * 1000,
            )

        # ── Step 3: Check provider availability ──────────────────────────
        if not provider.is_available():
            logger.warning(
                "RegistryEngine: provider unavailable for id=%s doc_type=%s provider=%s",
                verification_id, document_type, provider.provider_id,
            )
            src_t = getattr(provider, "source_type", ProviderSourceType.UNAVAILABLE)
            return self._build_error_response(
                verification_id=verification_id,
                document_type=document_type,
                registry_status=RegistryStatus.UNAVAILABLE,
                error_description=(
                    f"Registry provider '{provider.provider_id}' is currently unavailable. "
                    "The document cannot be checked against the registry at this time. "
                    "This does NOT indicate the document is invalid."
                ),
                elapsed_ms=(time.perf_counter() - t_start) * 1000,
                provider_id=provider.provider_id,
                source_type=src_t,
            )

        # ── Step 4: Build adapter request ─────────────────────────────────
        adapter = _get_adapter(document_type)
        request = adapter.build_request(
            verification_id=verification_id,
            session_data=session_data,
        )

        # Ensure query_hash is computed
        if not request.query_hash:
            doc_num_p = request.document_number
            doc_val = (doc_num_p.value if doc_num_p else "").strip().upper()
            q_ref = f"{document_type}:{doc_val}"
            request.query_hash = hashlib.sha256(q_ref.encode("utf-8")).hexdigest()

        # Check Cache
        if self.cache_enabled and request.query_hash:
            cached_resp = self.cache.get(document_type, request.query_hash, provider.provider_id)
            if cached_resp is not None:
                cached_resp.verification_id = verification_id
                if cached_resp.audit:
                    cached_resp.audit["verification_id"] = verification_id
                logger.info(
                    "RegistryEngine: returning cached response for id=%s hash=%s provider=%s",
                    verification_id, request.query_hash[:8], provider.provider_id,
                )
                return cached_resp

        # ── Step 5: Call provider ─────────────────────────────────────────
        try:
            response = provider.verify(request)
        except RegistryTimeout as exc:
            logger.warning(
                "RegistryEngine: timeout for id=%s provider=%s",
                verification_id, provider.provider_id,
            )
            return self._build_error_response(
                verification_id=verification_id,
                document_type=document_type,
                registry_status=RegistryStatus.TIMEOUT,
                error_description=(
                    "Registry provider call timed out. "
                    "The registry could not respond within the allowed time window."
                ),
                elapsed_ms=(time.perf_counter() - t_start) * 1000,
                provider_id=provider.provider_id,
            )
        except RegistryProviderUnavailable as exc:
            logger.warning(
                "RegistryEngine: provider unavailable (during call) for id=%s: %s",
                verification_id, exc,
            )
            return self._build_error_response(
                verification_id=verification_id,
                document_type=document_type,
                registry_status=RegistryStatus.UNAVAILABLE,
                error_description=str(exc),
                elapsed_ms=(time.perf_counter() - t_start) * 1000,
                provider_id=provider.provider_id,
            )
        except RegistryAuthenticationError as exc:
            # SECURITY: Do not log credential details
            logger.error(
                "RegistryEngine: authentication error for id=%s provider=%s",
                verification_id, provider.provider_id,
            )
            return self._build_error_response(
                verification_id=verification_id,
                document_type=document_type,
                registry_status=RegistryStatus.AUTHENTICATION_ERROR,
                error_description=(
                    "Registry authentication failed. "
                    "Contact system administration."
                ),
                elapsed_ms=(time.perf_counter() - t_start) * 1000,
                provider_id=provider.provider_id,
            )
        except RegistryResponseInvalid as exc:
            logger.error(
                "RegistryEngine: invalid provider response for id=%s: %s",
                verification_id, exc,
            )
            return self._build_error_response(
                verification_id=verification_id,
                document_type=document_type,
                registry_status=RegistryStatus.PROVIDER_ERROR,
                error_description=(
                    "Registry provider returned an invalid response. "
                    "The response failed schema validation."
                ),
                elapsed_ms=(time.perf_counter() - t_start) * 1000,
                provider_id=provider.provider_id,
            )
        except RegistryProviderError as exc:
            logger.error(
                "RegistryEngine: provider error for id=%s: %s",
                verification_id, exc,
            )
            return self._build_error_response(
                verification_id=verification_id,
                document_type=document_type,
                registry_status=RegistryStatus.PROVIDER_ERROR,
                error_description="Registry provider encountered an unexpected error.",
                elapsed_ms=(time.perf_counter() - t_start) * 1000,
                provider_id=provider.provider_id,
            )
        except Exception as exc:
            # Catch-all: never let provider exceptions propagate to the API
            # as unhandled 500 errors without capturing them in the evidence trail.
            logger.error(
                "RegistryEngine: unexpected error for id=%s: %s",
                verification_id, exc, exc_info=True,
            )
            return self._build_error_response(
                verification_id=verification_id,
                document_type=document_type,
                registry_status=RegistryStatus.PROVIDER_ERROR,
                error_description="An unexpected error occurred during registry verification.",
                elapsed_ms=(time.perf_counter() - t_start) * 1000,
                provider_id=getattr(provider, "provider_id", "unknown"),
            )

        elapsed_ms = (time.perf_counter() - t_start) * 1000

        if not response.query_hash and request.query_hash:
            response.query_hash = request.query_hash

        if not response.profile_version and document_type in ("driving_license", "drivinglicense"):
            response.profile_version = "0.9.0"

        if not response.field_comparisons and response.field_results:
            response.field_comparisons = [
                {
                    "field": fr.field,
                    "status": fr.status.value,
                    "document_value": fr.document_value,
                    "registry_value": fr.registry_value,
                    "is_critical": fr.is_critical,
                    "comparison_method": getattr(fr, "comparison_method", "strict"),
                    "note": fr.note,
                }
                for fr in response.field_results
            ]

        # Store in cache
        if self.cache_enabled and request.query_hash:
            self.cache.set(
                document_type=document_type,
                query_hash=request.query_hash,
                response=response,
                provider_id=provider.provider_id,
            )

        logger.info(
            "RegistryEngine: completed id=%s doc_type=%s status=%s elapsed_ms=%.1f",
            verification_id, document_type,
            response.registry.get("status", "UNKNOWN"),
            elapsed_ms,
        )

        return response

    def _build_error_response(
        self,
        verification_id: str,
        document_type: str,
        registry_status: RegistryStatus,
        error_description: str,
        elapsed_ms: float,
        provider_id: str = "unknown",
        source_type: Optional[ProviderSourceType] = None,
        query_hash: Optional[str] = None,
    ) -> RegistryVerificationResponse:
        """Build a structured error response that is safe to return to the API."""
        if not isinstance(source_type, (ProviderSourceType, str)):
            src_type = ProviderSourceType.DEVELOPMENT_MOCK
        else:
            try:
                src_type = ProviderSourceType(source_type)
            except ValueError:
                src_type = ProviderSourceType.DEVELOPMENT_MOCK
        return RegistryVerificationResponse(
            verification_id=verification_id,
            document_type=document_type,
            registry={
                "provider": provider_id,
                "status": registry_status.value,
                "record_found": False,
                "registry_document_status": None,
            },
            field_results=[],
            evidence=[
                RegistryEvidence(
                    type="registry_error",
                    severity="warning",
                    description=error_description,
                )
            ],
            provider_metadata=RegistryProviderMetadata(
                provider_id=provider_id,
                source_type=src_type,
                response_time_ms=round(elapsed_ms, 2),
            ),
            audit={
                "verification_id": verification_id,
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "document_type": document_type,
                "provider_id": provider_id,
                "registry_status": registry_status.value,
                "error": error_description,
                "response_time_ms": round(elapsed_ms, 2),
            },
            provider_type=src_type.value if hasattr(src_type, "value") else str(src_type),
            query_hash=query_hash,
            freshness={"cached": False, "is_fresh": False, "retrieved_at": None, "source": "error"},
            profile_version="0.9.0" if document_type in ("driving_license", "drivinglicense") else None,
            field_comparisons=[],
        )


# Singleton instance
registry_engine = RegistryEngine()
