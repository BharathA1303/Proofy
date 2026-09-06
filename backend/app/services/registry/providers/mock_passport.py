"""
backend/app/services/registry/providers/mock_passport.py

DEVELOPMENT MOCK PASSPORT REGISTRY PROVIDER

WARNING — DEVELOPMENT USE ONLY
================================
This is a SIMULATED registry with deterministic test records.
It is NOT connected to any real government database.
It is NOT Passport Seva, ICAO PKI, any immigration system, or any other
official registry.

This provider exists solely for local development and testing so that
the Registry Verification Engine can be exercised without requiring
access to a real authorized registry.

The production architecture allows an authorized government or
institutional registry provider to replace this mock by:
  1. Implementing RegistryProvider in a new file
  2. Setting REGISTRY_PROVIDER_PASSPORT=authorized_api in config
  3. Zero changes to the engine, risk engine, or frontend

source_type is always "development_mock" for this provider.
The UI must NEVER display this as "Government Verified".

===========================
DEVELOPMENT MOCK RECORDS
===========================

  TESTPASS001    → ACTIVE   (all fields match correctly)
  TESTEXPIRED001 → EXPIRED  (document expired in registry)
  TESTREVOKED001 → REVOKED  (document revoked in registry)
  TESTMISMATCH001→ ACTIVE   (found, but name/DOB intentionally different)
  TESTSUSPENDED001 → SUSPENDED
  (any other)    → NOT_FOUND
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from app.schemas.registry import (
    ProviderSourceType,
    RegistryProviderStatus,
    RegistryRecord,
    RegistryStatus,
    RegistryVerificationRequest,
    RegistryVerificationResponse,
    RegistryEvidence,
    RegistryFieldResult,
    RegistryProviderMetadata,
)
from app.services.registry.base import RegistryProvider
from app.services.registry.comparator import compare_fields

logger = logging.getLogger(__name__)

# ── Simulated latency for realistic behavior ───────────────────────────────────

_MOCK_LATENCY_MS = 8.0   # Fixed latency for test predictability

# ──────────────────────────────────────────────────────────────────────────────
#  DEVELOPMENT MOCK DATA
#  These records are fictional. No real person's data is represented.
# ──────────────────────────────────────────────────────────────────────────────

_MOCK_RECORDS: dict[str, dict] = {

    # RECORD A: Active, all fields correctly populated
    "TESTPASS001": {
        "document_number": "TESTPASS001",
        "registry_document_status": "ACTIVE",
        "name": "TEST USER ONE",
        "date_of_birth": "1990-01-01",
        "nationality": "IND",
        "expiry_date": "2030-01-01",
        "issuing_authority": "DEVELOPMENT MOCK AUTHORITY",
        "gender": "M",
    },

    # RECORD B: Expired according to registry
    "TESTEXPIRED001": {
        "document_number": "TESTEXPIRED001",
        "registry_document_status": "EXPIRED",
        "name": "TEST EXPIRED",
        "date_of_birth": "1985-06-15",
        "nationality": "IND",
        "expiry_date": "2020-01-01",
        "issuing_authority": "DEVELOPMENT MOCK AUTHORITY",
        "gender": "F",
    },

    # RECORD C: Revoked — significant downstream risk signal
    "TESTREVOKED001": {
        "document_number": "TESTREVOKED001",
        "registry_document_status": "REVOKED",
        "name": "TEST REVOKED",
        "date_of_birth": "1975-03-20",
        "nationality": "IND",
        "expiry_date": "2028-03-20",
        "issuing_authority": "DEVELOPMENT MOCK AUTHORITY",
        "gender": "M",
    },

    # RECORD D: Active, but identity fields intentionally mismatch the document
    # Used to test MISMATCH detection
    "TESTMISMATCH001": {
        "document_number": "TESTMISMATCH001",
        "registry_document_status": "ACTIVE",
        "name": "DIFFERENT NAME ENTIRELY",    # intentionally different
        "date_of_birth": "1984-06-15",        # intentionally different year
        "nationality": "USA",                  # intentionally different
        "expiry_date": "2029-01-01",
        "issuing_authority": "DEVELOPMENT MOCK AUTHORITY",
        "gender": "M",
    },

    # RECORD E: Suspended
    "TESTSUSPENDED001": {
        "document_number": "TESTSUSPENDED001",
        "registry_document_status": "SUSPENDED",
        "name": "TEST SUSPENDED",
        "date_of_birth": "1980-12-10",
        "nationality": "IND",
        "expiry_date": "2031-12-10",
        "issuing_authority": "DEVELOPMENT MOCK AUTHORITY",
        "gender": "F",
    },

    # RECORD F: Active, all fields populated for secondary testing
    "TESTAMBIGUOUS001": {
        "document_number": "TESTAMBIGUOUS001",
        "registry_document_status": "ACTIVE",
        "name": "TEST AMBIGUOUS",
        "date_of_birth": "1992-07-04",
        "nationality": "IND",
        "expiry_date": "2032-07-04",
        "issuing_authority": "DEVELOPMENT MOCK AUTHORITY",
        "gender": "M",
    },

    # TESTNOTFOUND001 — not in dict → returns NOT_FOUND
}


class MockPassportRegistryProvider(RegistryProvider):
    """
    DEVELOPMENT MOCK Passport Registry Provider.

    Returns deterministic results from _MOCK_RECORDS.
    Documents not in the mock database return NOT_FOUND.

    CRITICAL DISCLAIMER:
      This is simulated data for development and testing purposes.
      It is NOT connected to any government registry.
      Do NOT deploy this as a real registry integration.
      source_type is always "development_mock".
    """

    _PROVIDER_ID = "mock-passport-registry-v1"
    _SUPPORTED_TYPES = {"passport"}
    _available = True

    def __init__(self) -> None:
        self._initialized = False

    @property
    def provider_id(self) -> str:
        return self._PROVIDER_ID

    def initialize(self) -> None:
        """No external connection needed for mock provider."""
        self._initialized = True
        logger.info(
            "MockPassportRegistryProvider initialized. "
            "DEVELOPMENT MOCK — not a real government registry. "
            "Available test records: %s",
            list(_MOCK_RECORDS.keys()),
        )

    def is_available(self) -> bool:
        """Mock provider is always available (no network dependency)."""
        return self._available and self._initialized

    def supports(self, document_type: str) -> bool:
        return document_type in self._SUPPORTED_TYPES

    def health_check(self) -> RegistryProviderStatus:
        return RegistryProviderStatus(
            provider_id=self._PROVIDER_ID,
            source_type=ProviderSourceType.DEVELOPMENT_MOCK,
            available=self.is_available(),
            supported_document_types=list(self._SUPPORTED_TYPES),
            details=(
                "Development mock provider. "
                "NOT a real government registry. "
                f"Active test records: {list(_MOCK_RECORDS.keys())}"
            ),
        )

    def verify(
        self,
        request: RegistryVerificationRequest,
    ) -> RegistryVerificationResponse:
        """
        Execute mock registry verification.

        Looks up the document number in the mock database.
        Returns deterministic results based on the test record.

        Simulates realistic provider latency.
        """
        t_start = time.perf_counter()

        # Simulate a small processing delay
        time.sleep(_MOCK_LATENCY_MS / 1000.0)

        # Extract document number from request
        doc_num_provenance = request.document_number
        doc_num = doc_num_provenance.value if doc_num_provenance else None

        # Normalize for lookup
        lookup_key = (doc_num or "").strip().upper()

        t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        logger.info(
            "MockPassportRegistry lookup: id=%s doc_num=%s",
            request.verification_id, lookup_key,
        )

        # ── NOT FOUND ─────────────────────────────────────────────────────
        if not lookup_key or lookup_key not in _MOCK_RECORDS:
            return self._build_response(
                request=request,
                registry_status=RegistryStatus.NOT_FOUND,
                record=None,
                field_results=[],
                evidence=[
                    RegistryEvidence(
                        type="registry_lookup",
                        severity="info",
                        description=(
                            f"No development mock registry record found for document number "
                            f"'{lookup_key}'. This is a development sandbox result."
                        ),
                    )
                ],
                response_time_ms=t_elapsed_ms,
            )

        # ── RECORD FOUND — build normalized registry record ───────────────
        raw = _MOCK_RECORDS[lookup_key]
        record = RegistryRecord(
            document_number=raw.get("document_number"),
            name=raw.get("name"),
            date_of_birth=raw.get("date_of_birth"),
            nationality=raw.get("nationality"),
            expiry_date=raw.get("expiry_date"),
            issuing_authority=raw.get("issuing_authority"),
            gender=raw.get("gender"),
            registry_document_status=raw.get("registry_document_status", "UNKNOWN"),
        )

        # ── Run field comparator to determine status and field evidence ────
        field_results, registry_status = compare_fields(request, record)

        # ── Build evidence list ────────────────────────────────────────────
        evidence = _build_evidence(registry_status, field_results, lookup_key)

        t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        logger.info(
            "MockPassportRegistry result: id=%s doc_num=%s status=%s",
            request.verification_id, lookup_key, registry_status,
        )

        return self._build_response(
            request=request,
            registry_status=registry_status,
            record=record,
            field_results=field_results,
            evidence=evidence,
            response_time_ms=t_elapsed_ms,
        )

    def _build_response(
        self,
        request: RegistryVerificationRequest,
        registry_status: RegistryStatus,
        record: Optional[RegistryRecord],
        field_results: list[RegistryFieldResult],
        evidence: list[RegistryEvidence],
        response_time_ms: float,
    ) -> RegistryVerificationResponse:
        """Assemble the normalized response."""
        import datetime

        return RegistryVerificationResponse(
            verification_id=request.verification_id,
            document_type=request.document_type,
            registry={
                "provider": self._PROVIDER_ID,
                "status": registry_status.value,
                "record_found": record is not None,
                "registry_document_status": (
                    record.registry_document_status if record else None
                ),
            },
            field_results=field_results,
            evidence=evidence,
            provider_metadata=RegistryProviderMetadata(
                provider_id=self._PROVIDER_ID,
                source_type=ProviderSourceType.DEVELOPMENT_MOCK,
                response_time_ms=round(response_time_ms, 2),
            ),
            audit={
                "verification_id": request.verification_id,
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "document_type": request.document_type,
                "provider_id": self._PROVIDER_ID,
                "source_type": ProviderSourceType.DEVELOPMENT_MOCK.value,
                "registry_status": registry_status.value,
                "record_found": record is not None,
                "response_time_ms": round(response_time_ms, 2),
                "disclaimer": (
                    "DEVELOPMENT MOCK DATA — not a real government registry result."
                ),
            },
        )


def _build_evidence(
    registry_status: RegistryStatus,
    field_results: list[RegistryFieldResult],
    doc_num: str,
) -> list[RegistryEvidence]:
    """Build structured evidence items based on registry status and field results."""
    evidence: list[RegistryEvidence] = []

    from app.schemas.registry import FieldMatchStatus

    if registry_status == RegistryStatus.MATCHED:
        evidence.append(RegistryEvidence(
            type="registry_record",
            severity="info",
            description=(
                f"Development sandbox record located for '{doc_num}' and "
                "identity fields matched. This is a development mock result."
            ),
        ))
    elif registry_status == RegistryStatus.NOT_FOUND:
        evidence.append(RegistryEvidence(
            type="registry_lookup",
            severity="warning",
            description=(
                f"No development sandbox record found for '{doc_num}'. "
                "NOT_FOUND is not equivalent to INVALID or FORGED. "
                "The Risk Engine determines how to weight this signal."
            ),
        ))
    elif registry_status == RegistryStatus.REVOKED:
        evidence.append(RegistryEvidence(
            type="registry_status",
            severity="critical",
            description=(
                f"Development sandbox reports document '{doc_num}' as REVOKED. "
                "This is a significant downstream risk signal for the Risk Engine."
            ),
        ))
    elif registry_status == RegistryStatus.SUSPENDED:
        evidence.append(RegistryEvidence(
            type="registry_status",
            severity="critical",
            description=(
                f"Development sandbox reports document '{doc_num}' as SUSPENDED."
            ),
        ))
    elif registry_status == RegistryStatus.EXPIRED:
        evidence.append(RegistryEvidence(
            type="registry_status",
            severity="warning",
            description=(
                f"Development sandbox reports document '{doc_num}' as EXPIRED "
                "in the registry. Note: registry expiry is separate from document "
                "structure expiry validation (Module 2)."
            ),
        ))
    elif registry_status == RegistryStatus.MISMATCH:
        mismatched = [
            r.field for r in field_results
            if r.status == FieldMatchStatus.MISMATCH and r.is_critical
        ]
        evidence.append(RegistryEvidence(
            type="field_mismatch",
            severity="critical",
            description=(
                f"Registry record found but critical identity fields differ: "
                f"{', '.join(mismatched)}. This requires Risk Engine evaluation."
            ),
        ))
    elif registry_status == RegistryStatus.INCONCLUSIVE:
        evidence.append(RegistryEvidence(
            type="registry_record",
            severity="warning",
            description=(
                "Registry record found but insufficient comparable fields to "
                "determine a definitive match."
            ),
        ))

    # Add disclaimer evidence item for mock mode
    evidence.append(RegistryEvidence(
        type="provider_disclaimer",
        severity="info",
        description=(
            "DEVELOPMENT SANDBOX RESULT — This data is from a simulated mock registry. "
            "It is NOT from a real government database. "
            "Production deployment requires an authorized registry provider."
        ),
    ))

    return evidence
