"""
backend/app/services/registry/providers/mock_border_permit.py

Development Mock Registry Provider for Border Permits.

DEVELOPMENT USE ONLY — Not a real government immigration or border control database.
Visibly identifies itself as DEVELOPMENT_MOCK.
"""
from __future__ import annotations

import datetime
import logging
import time
from typing import Optional

from app.core.exceptions import RegistryProviderUnavailable, RegistryTimeout
from app.schemas.registry import (
    FieldMatchStatus,
    ProviderSourceType,
    RegistryEvidence,
    RegistryFieldResult,
    RegistryProviderMetadata,
    RegistryProviderStatus,
    RegistryRecord,
    RegistryStatus,
    RegistryVerificationRequest,
    RegistryVerificationResponse,
)
from app.services.documents.border_permit.border_permit_field_normalizer import (
    normalize_permit_number,
)
from app.services.registry.base import RegistryProvider
from app.services.registry.comparator import compare_fields

logger = logging.getLogger(__name__)

_MOCK_LATENCY_MS = 50.0

_MOCK_BP_RECORDS: dict[str, dict] = {
    # Active valid Border Permit matching test sample
    "TESTBP001": {
        "document_number": "TESTBP001",
        "registry_document_status": "ACTIVE",
        "name": "ALEX DUPONT",
        "date_of_birth": "1990-08-12",
        "expiry_date": "2026-12-31",
        "issuing_authority": "Border Management Authority",
        "passport_number": "P1234567",
    },
    # Synthetic canonical permit number
    "BP2026000123": {
        "document_number": "BP2026000123",
        "registry_document_status": "ACTIVE",
        "name": "ALEX DUPONT",
        "date_of_birth": "1990-08-12",
        "expiry_date": "2026-12-31",
        "issuing_authority": "Border Management Authority",
        "passport_number": "P1234567",
    },
    # Expired status test record
    "TESTBPEXPIRED001": {
        "document_number": "TESTBPEXPIRED001",
        "registry_document_status": "EXPIRED",
        "name": "TEST EXPIRED",
        "date_of_birth": "1980-01-01",
        "expiry_date": "2020-01-01",
        "issuing_authority": "Border Management Authority",
    },
    # Revoked status test record
    "TESTBPREVOKED001": {
        "document_number": "TESTBPREVOKED001",
        "registry_document_status": "REVOKED",
        "name": "TEST REVOKED",
        "date_of_birth": "1975-06-15",
        "expiry_date": "2027-01-01",
        "issuing_authority": "Border Management Authority",
    },
    # Suspended status test record
    "TESTBPSUSPENDED001": {
        "document_number": "TESTBPSUSPENDED001",
        "registry_document_status": "SUSPENDED",
        "name": "TEST SUSPENDED",
        "date_of_birth": "1988-10-20",
        "expiry_date": "2026-06-30",
        "issuing_authority": "Border Management Authority",
    },
    # Mismatch test record (name discrepancy)
    "TESTBPMISMATCH001": {
        "document_number": "TESTBPMISMATCH001",
        "registry_document_status": "ACTIVE",
        "name": "COMPLETELY DIFFERENT PERSON",
        "date_of_birth": "1990-08-12",
        "expiry_date": "2026-12-31",
        "issuing_authority": "Border Management Authority",
    },
}


class MockBorderPermitRegistryProvider(RegistryProvider):
    """
    In-memory mock registry provider for Border Permit verification.
    """

    def __init__(self) -> None:
        self._provider_id = "mock_border_permit_registry"
        self._is_initialized = False
        self._available = True
        self._supported_types = {"border_permit", "borderpermit"}

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def initialize(self) -> None:
        self._is_initialized = True
        logger.info(
            "MockBorderPermitRegistryProvider initialized: provider_id=%s (DEVELOPMENT MOCK — not real government DB)",
            self._provider_id,
        )

    def is_available(self) -> bool:
        return self._available

    def supports(self, document_type: str) -> bool:
        return document_type.lower() in self._supported_types

    def health_check(self) -> RegistryProviderStatus:
        return RegistryProviderStatus(
            provider_id=self._provider_id,
            source_type=ProviderSourceType.DEVELOPMENT_MOCK,
            available=self.is_available(),
            supported_document_types=list(self._supported_types),
            details=(
                "Development mock provider for Border Permit. "
                "NOT a real government registry."
            ),
        )

    def verify(self, request: RegistryVerificationRequest) -> RegistryVerificationResponse:
        t_start = time.perf_counter()

        if not self._is_initialized:
            self.initialize()

        raw_num = request.document_number.value if request.document_number else None
        doc_num, _ = normalize_permit_number(raw_num)
        doc_num_key = doc_num.upper() if doc_num else ""

        logger.info(
            "MockBorderPermitRegistry lookup: id=%s doc_num=%s",
            request.verification_id, doc_num_key,
        )

        # 1. Error simulation
        if doc_num_key == "TESTBPTIMEOUT001":
            time.sleep(0.01)
            logger.warning("MockBorderPermitRegistry: simulating timeout for %s", request.verification_id)
            raise RegistryTimeout(f"Mock Border Permit registry timed out querying {doc_num_key}")

        if doc_num_key == "TESTBPUNAVAIL001":
            logger.warning("MockBorderPermitRegistry: simulating unavailable for %s", request.verification_id)
            raise RegistryProviderUnavailable(f"Mock Border Permit registry unavailable for {doc_num_key}")

        # Simulate standard network latency
        time.sleep(_MOCK_LATENCY_MS / 1000.0)
        t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        # 2. Record lookup
        if doc_num_key not in _MOCK_BP_RECORDS:
            logger.info("MockBorderPermitRegistry: record NOT_FOUND for doc_num=%s", doc_num_key)
            return self._build_response(
                request=request,
                registry_status=RegistryStatus.NOT_FOUND,
                record=None,
                field_results=[],
                evidence=[
                    RegistryEvidence(
                        type="registry_lookup",
                        severity="warning",
                        description=f"No development sandbox record found for border permit '{doc_num_key}'.",
                    )
                ],
                response_time_ms=t_elapsed_ms,
            )

        record_data = _MOCK_BP_RECORDS[doc_num_key]
        reg_record = RegistryRecord(
            document_number=record_data["document_number"],
            registry_document_status=record_data.get("registry_document_status", "ACTIVE"),
            name=record_data.get("name"),
            date_of_birth=record_data.get("date_of_birth"),
            nationality=record_data.get("nationality"),
            expiry_date=record_data.get("expiry_date"),
            issuing_authority=record_data.get("issuing_authority"),
        )

        field_results, status = compare_fields(request, reg_record)
        evidence = _build_evidence(status, field_results, doc_num_key)

        t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        return self._build_response(
            request=request,
            registry_status=status,
            record=reg_record,
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
        return RegistryVerificationResponse(
            verification_id=request.verification_id,
            document_type=request.document_type,
            registry={
                "provider": self._provider_id,
                "status": registry_status.value,
                "record_found": record is not None,
                "registry_document_status": (
                    record.registry_document_status if record else None
                ),
            },
            field_results=field_results,
            evidence=evidence,
            provider_metadata=RegistryProviderMetadata(
                provider_id=self._provider_id,
                source_type=ProviderSourceType.DEVELOPMENT_MOCK,
                response_time_ms=round(response_time_ms, 2),
            ),
            audit={
                "verification_id": request.verification_id,
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "document_type": request.document_type,
                "provider_id": self._provider_id,
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
    evidence: list[RegistryEvidence] = []
    if registry_status == RegistryStatus.MATCHED:
        evidence.append(RegistryEvidence(
            type="registry_record",
            severity="info",
            description=(
                f"Development sandbox record located for border permit '{doc_num}' and "
                "identity fields matched. This is a development mock result."
            ),
        ))
    elif registry_status == RegistryStatus.NOT_FOUND:
        evidence.append(RegistryEvidence(
            type="registry_lookup",
            severity="warning",
            description=f"No development sandbox record found for border permit '{doc_num}'.",
        ))
    elif registry_status == RegistryStatus.REVOKED:
        evidence.append(RegistryEvidence(
            type="registry_status",
            severity="critical",
            description=f"Development sandbox reports border permit '{doc_num}' as REVOKED.",
        ))
    elif registry_status == RegistryStatus.SUSPENDED:
        evidence.append(RegistryEvidence(
            type="registry_status",
            severity="critical",
            description=f"Development sandbox reports border permit '{doc_num}' as SUSPENDED.",
        ))
    elif registry_status == RegistryStatus.EXPIRED:
        evidence.append(RegistryEvidence(
            type="registry_status",
            severity="warning",
            description=f"Development sandbox reports border permit '{doc_num}' as EXPIRED.",
        ))
    elif registry_status == RegistryStatus.MISMATCH:
        mismatched = [r.field for r in field_results if r.status == FieldMatchStatus.MISMATCH]
        evidence.append(RegistryEvidence(
            type="field_mismatch",
            severity="critical",
            description=(
                f"Registry record found for border permit '{doc_num}' but fields differ: "
                f"{', '.join(mismatched)}."
            ),
        ))
    return evidence
