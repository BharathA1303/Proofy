"""
backend/app/services/registry/providers/mock_visa.py

Development Mock Registry Provider for Visa Documents.

DEVELOPMENT USE ONLY — Not a real government or immigration database.
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
from app.services.registry.base import RegistryProvider
from app.services.registry.comparator import compare_fields

logger = logging.getLogger(__name__)

_MOCK_LATENCY_MS = 50.0

_MOCK_VISA_RECORDS: dict[str, dict] = {
    # Pre-populated Synthetic Reference Registry (Official & Blacklist)
    "V1002003": {
        "document_number": "V1002003",
        "registry_document_status": "ACTIVE",
        "name": "AARAV SHARMA",
        "date_of_birth": "1990-05-15",
        "nationality": "IND",
        "expiry_date": "2028-01-31",
        "issuing_authority": "CONSULAR SECTION DELHI",
        "gender": "M",
        "passport_number": "Z1234567",
        "visa_type": "BUSINESS",
    },
    "V7008009": {
        "document_number": "V7008009",
        "registry_document_status": "REVOKED",
        "name": "VIKRAM MALHOTRA",
        "date_of_birth": "1982-11-20",
        "nationality": "IND",
        "expiry_date": "2027-05-09",
        "issuing_authority": "CONSULAR SECTION MUMBAI",
        "gender": "M",
        "passport_number": "Z7654321",
        "visa_type": "TOURIST",
    },
    "TESTVISA001": {
        "document_number": "TESTVISA001",
        "registry_document_status": "ACTIVE",
        "name": "SARAH CONNOR",
        "date_of_birth": "1985-05-12",
        "nationality": "USA",
        "expiry_date": "2033-01-15",
        "issuing_authority": "EMBASSY LONDON",
        "gender": "F",
        "passport_number": "P9876543",
        "visa_type": "B1/B2",
    },
    # Expired visa
    "TESTVISAEXPIRED001": {
        "document_number": "TESTVISAEXPIRED001",
        "registry_document_status": "EXPIRED",
        "name": "TEST EXPIRED",
        "date_of_birth": "1980-01-01",
        "nationality": "GBR",
        "expiry_date": "2020-01-01",
        "issuing_authority": "CONSULAR POST SYNTHETIC",
        "passport_number": "T1111111",
        "visa_type": "TOURIST",
    },
    # Revoked visa
    "TESTVISAREVOKED001": {
        "document_number": "TESTVISAREVOKED001",
        "registry_document_status": "REVOKED",
        "name": "TEST REVOKED",
        "date_of_birth": "1975-06-15",
        "nationality": "CAN",
        "expiry_date": "2028-06-15",
        "issuing_authority": "CONSULAR POST SYNTHETIC",
        "passport_number": "T2222222",
        "visa_type": "BUSINESS",
    },
    # Mismatch visa (active but fields differ)
    "TESTVISAMISMATCH001": {
        "document_number": "TESTVISAMISMATCH001",
        "registry_document_status": "ACTIVE",
        "name": "COMPLETELY DIFFERENT PERSON",
        "date_of_birth": "1960-05-10",
        "nationality": "USA",
        "expiry_date": "2030-05-10",
        "issuing_authority": "CONSULAR POST SYNTHETIC",
        "passport_number": "WRONGPPT999",
        "visa_type": "TOURIST",
    },
    # Suspended visa
    "TESTVISASUSPENDED001": {
        "document_number": "TESTVISASUSPENDED001",
        "registry_document_status": "SUSPENDED",
        "name": "TEST SUSPENDED",
        "date_of_birth": "1992-11-20",
        "nationality": "IND",
        "expiry_date": "2029-11-20",
        "issuing_authority": "CONSULAR POST SYNTHETIC",
        "passport_number": "T3333333",
        "visa_type": "WORK",
    },
}


class MockVisaRegistryProvider(RegistryProvider):
    """
    Mock Visa registry provider for development and testing.
    """

    _PROVIDER_ID = "mock_visa_registry"
    _SUPPORTED_TYPES = {"visa"}

    def __init__(self) -> None:
        self._available = True

    @property
    def provider_id(self) -> str:
        return self._PROVIDER_ID

    def initialize(self) -> None:
        logger.info(
            "MockVisaRegistryProvider initialized: provider_id=%s (DEVELOPMENT MOCK — not real government DB)",
            self._PROVIDER_ID,
        )

    def is_available(self) -> bool:
        return self._available

    def supports(self, document_type: str) -> bool:
        return document_type.lower() in self._SUPPORTED_TYPES

    def health_check(self) -> RegistryProviderStatus:
        return RegistryProviderStatus(
            provider_id=self._PROVIDER_ID,
            source_type=ProviderSourceType.DEVELOPMENT_MOCK,
            available=self.is_available(),
            supported_document_types=list(self._SUPPORTED_TYPES),
            details=(
                "Development mock provider for Visa. "
                "NOT a real government registry. "
                f"Active test records: {list(_MOCK_VISA_RECORDS.keys())}"
            ),
        )

    def verify(self, request: RegistryVerificationRequest) -> RegistryVerificationResponse:
        t_start = time.perf_counter()
        time.sleep(_MOCK_LATENCY_MS / 1000.0)

        doc_num_provenance = request.document_number
        doc_num = doc_num_provenance.value if doc_num_provenance else None
        lookup_key = (doc_num or "").strip().upper()

        t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        logger.info(
            "MockVisaRegistry lookup: id=%s doc_num=%s",
            request.verification_id, lookup_key,
        )

        if lookup_key == "TESTVISATIMEOUT001":
            raise RegistryTimeout(f"Mock visa registry timed out querying {lookup_key}")
        if lookup_key == "TESTVISAUNAVAIL001":
            raise RegistryProviderUnavailable(f"Mock visa registry unavailable for {lookup_key}")

        # NOT FOUND
        if not lookup_key or lookup_key not in _MOCK_VISA_RECORDS:
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
                            f"No development mock registry record found for visa number "
                            f"'{lookup_key}'. This is a development sandbox result."
                        ),
                    )
                ],
                response_time_ms=t_elapsed_ms,
            )

        # RECORD FOUND
        raw = _MOCK_VISA_RECORDS[lookup_key]
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

        field_results, registry_status = compare_fields(request, record)
        evidence = _build_evidence(registry_status, field_results, lookup_key)

        t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0

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
    evidence: list[RegistryEvidence] = []

    if registry_status == RegistryStatus.MATCHED:
        evidence.append(RegistryEvidence(
            type="registry_record",
            severity="info",
            description=(
                f"Development sandbox record located for visa '{doc_num}' and "
                "identity fields matched. This is a development mock result."
            ),
        ))
    elif registry_status == RegistryStatus.NOT_FOUND:
        evidence.append(RegistryEvidence(
            type="registry_lookup",
            severity="warning",
            description=(
                f"No development sandbox record found for visa '{doc_num}'."
            ),
        ))
    elif registry_status == RegistryStatus.REVOKED:
        evidence.append(RegistryEvidence(
            type="registry_status",
            severity="critical",
            description=(
                f"Development sandbox reports visa '{doc_num}' as REVOKED."
            ),
        ))
    elif registry_status == RegistryStatus.SUSPENDED:
        evidence.append(RegistryEvidence(
            type="registry_status",
            severity="critical",
            description=(
                f"Development sandbox reports visa '{doc_num}' as SUSPENDED."
            ),
        ))
    elif registry_status == RegistryStatus.EXPIRED:
        evidence.append(RegistryEvidence(
            type="registry_status",
            severity="warning",
            description=(
                f"Development sandbox reports visa '{doc_num}' as EXPIRED."
            ),
        ))
    elif registry_status == RegistryStatus.MISMATCH:
        mismatches = [fr.field for fr in field_results if fr.status == FieldMatchStatus.MISMATCH]
        evidence.append(RegistryEvidence(
            type="registry_mismatch",
            severity="high",
            description=(
                f"Visa '{doc_num}' record found in sandbox, but field mismatch in: "
                f"{', '.join(mismatches)}."
            ),
        ))
    else:
        evidence.append(RegistryEvidence(
            type="registry_status",
            severity="info",
            description=f"Registry status: {registry_status.value}.",
        ))

    return evidence
