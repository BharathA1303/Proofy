"""
backend/app/services/registry/providers/mock_driving_license.py

Development Mock Registry Provider for Driving License Documents.

DEVELOPMENT USE ONLY — Not a real government transport database (e.g. Parivahan/Sarathi).
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
from app.services.registry.base import RegistryProvider
from app.services.registry.comparator import compare_fields

logger = logging.getLogger(__name__)

_MOCK_LATENCY_MS = 50.0

_MOCK_DL_RECORDS: dict[str, dict] = {
    # Active valid DL matching standard test sample
    "TESTDL001": {
        "document_number": "TESTDL001",
        "registry_document_status": "ACTIVE",
        "name": "RAHUL SHARMA",
        "date_of_birth": "1992-05-15",
        "expiry_date": "2035-05-14",
        "issuing_authority": "RTO DELHI",
        "blood_group": "O+",
        "vehicle_classes": "LMV, MCWG",
    },
    # Genuine User Driving License: BHARATH A (Government of Tamil Nadu)
    "TN0520250014128": {
        "document_number": "TN0520250014128",
        "registry_document_status": "ACTIVE",
        "name": "BHARATH A",
        "date_of_birth": "2007-03-13",
        "expiry_date": "2047-03-12",
        "issuing_authority": "GOVERNMENT OF TAMIL NADU",
        "blood_group": "A1B+",
        "vehicle_classes": "LMV, MCWG",
    },
    "TN05 20250014128": {
        "document_number": "TN05 20250014128",
        "registry_document_status": "ACTIVE",
        "name": "BHARATH A",
        "date_of_birth": "2007-03-13",
        "expiry_date": "2047-03-12",
        "issuing_authority": "GOVERNMENT OF TAMIL NADU",
        "blood_group": "A1B+",
        "vehicle_classes": "LMV, MCWG",
    },
    # Pre-populated Synthetic Reference Registry (Official & Blacklist)
    "DL-0420230012345": {
        "document_number": "DL-0420230012345",
        "registry_document_status": "ACTIVE",
        "name": "PRIYA SUNDAR",
        "date_of_birth": "1994-03-22",
        "expiry_date": "2034-03-21",
        "issuing_authority": "RTO DELHI CENTRAL",
        "blood_group": "B+",
        "vehicle_classes": "MCWG, LMV",
    },
    "DL0420230012345": {
        "document_number": "DL0420230012345",
        "registry_document_status": "ACTIVE",
        "name": "PRIYA SUNDAR",
        "date_of_birth": "1994-03-22",
        "expiry_date": "2034-03-21",
        "issuing_authority": "RTO DELHI CENTRAL",
        "blood_group": "B+",
        "vehicle_classes": "MCWG, LMV",
    },
    "DL-0120180099887": {
        "document_number": "DL-0120180099887",
        "registry_document_status": "REVOKED",
        "name": "KABIR MEHTA",
        "date_of_birth": "1986-07-14",
        "expiry_date": "2038-07-13",
        "issuing_authority": "RTO MUMBAI WEST",
        "blood_group": "O+",
        "vehicle_classes": "MCWG, LMV",
    },
    "DL0120180099887": {
        "document_number": "DL0120180099887",
        "registry_document_status": "REVOKED",
        "name": "KABIR MEHTA",
        "date_of_birth": "1986-07-14",
        "expiry_date": "2038-07-13",
        "issuing_authority": "RTO MUMBAI WEST",
        "blood_group": "O+",
        "vehicle_classes": "MCWG, LMV",
    },
    # Expired DL
    "TESTDLEXPIRED001": {
        "document_number": "TESTDLEXPIRED001",
        "registry_document_status": "EXPIRED",
        "name": "TEST EXPIRED",
        "date_of_birth": "1980-01-01",
        "expiry_date": "2020-01-01",
        "issuing_authority": "RTO CHENNAI",
    },
    # Revoked DL
    "TESTDLREVOKED001": {
        "document_number": "TESTDLREVOKED001",
        "registry_document_status": "REVOKED",
        "name": "TEST REVOKED",
        "date_of_birth": "1975-06-15",
        "expiry_date": "2028-06-15",
        "issuing_authority": "RTO MUMBAI",
    },
    # Suspended DL
    "TESTDLSUSPENDED001": {
        "document_number": "TESTDLSUSPENDED001",
        "registry_document_status": "SUSPENDED",
        "name": "TEST SUSPENDED",
        "date_of_birth": "1988-10-20",
        "expiry_date": "2030-10-20",
        "issuing_authority": "RTO BANGALORE",
    },
    # Mismatch DL (active record exists, but holder details differ)
    "TESTDLMISMATCH001": {
        "document_number": "TESTDLMISMATCH001",
        "registry_document_status": "ACTIVE",
        "name": "VIKRAM SINGH",
        "date_of_birth": "1965-03-12",
        "expiry_date": "2032-03-12",
        "issuing_authority": "RTO JAIPUR",
    },
}


class MockDrivingLicenseRegistryProvider(RegistryProvider):
    """
    Mock Driving License registry provider for development and testing.
    Emulates an RTO database lookup for Indian Driving Licences.
    """

    _PROVIDER_ID = "mock_driving_license_registry"
    _SUPPORTED_TYPES = {"driving_license", "drivinglicense"}

    def __init__(self) -> None:
        self._available = True

    @property
    def provider_id(self) -> str:
        return self._PROVIDER_ID

    def initialize(self) -> None:
        logger.info(
            "MockDrivingLicenseRegistryProvider initialized: provider_id=%s (DEVELOPMENT MOCK — not real government DB)",
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
                "Development mock provider for Driving License. "
                "NOT a real government registry. "
                f"Active test records: {list(_MOCK_DL_RECORDS.keys())}"
            ),
        )

    def verify(self, request: RegistryVerificationRequest) -> RegistryVerificationResponse:
        t_start = time.perf_counter()
        time.sleep(_MOCK_LATENCY_MS / 1000.0)

        doc_num_provenance = request.document_number
        doc_num = doc_num_provenance.value if doc_num_provenance else None
        if not doc_num and request.traveler:
            doc_num = getattr(request.traveler, "licenseNumber", None) or getattr(request.traveler, "docNumber", None)
        lookup_key = (doc_num or "").strip().upper()

        t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        logger.info(
            "MockDrivingLicenseRegistry lookup: id=%s doc_num=%s",
            request.verification_id, lookup_key,
        )

        if lookup_key == "TESTDLTIMEOUT001":
            raise RegistryTimeout(f"Mock driving license registry timed out querying {lookup_key}")
        if lookup_key == "TESTDLUNAVAIL001":
            raise RegistryProviderUnavailable(f"Mock driving license registry unavailable for {lookup_key}")

        # NOT FOUND check (support space/hyphen variation e.g. "TN05 2025..." vs "TN052025..." or "DL-04...")
        if lookup_key not in _MOCK_DL_RECORDS:
            compact = lookup_key.replace(" ", "").replace("-", "")
            if compact in _MOCK_DL_RECORDS:
                lookup_key = compact
            else:
                for k in _MOCK_DL_RECORDS:
                    if k.replace(" ", "").replace("-", "") == compact:
                        lookup_key = k
                        break

        if not lookup_key or lookup_key not in _MOCK_DL_RECORDS:
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
                            f"No development mock registry record found for driving license number "
                            f"'{lookup_key}'. This is a development sandbox result."
                        ),
                    )
                ],
                response_time_ms=t_elapsed_ms,
            )

        raw_record = _MOCK_DL_RECORDS[lookup_key]
        reg_record = RegistryRecord(
            document_number=raw_record["document_number"],
            registry_document_status=raw_record.get("registry_document_status", "ACTIVE"),
            name=raw_record.get("name"),
            date_of_birth=raw_record.get("date_of_birth"),
            expiry_date=raw_record.get("expiry_date"),
            issuing_authority=raw_record.get("issuing_authority"),
        )

        field_results, status = compare_fields(request, reg_record)
        evidence = _build_evidence(status, field_results, lookup_key)

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
                f"Development sandbox record located for driving license '{doc_num}' and "
                "identity fields matched. This is a development mock result."
            ),
        ))
    elif registry_status == RegistryStatus.NOT_FOUND:
        evidence.append(RegistryEvidence(
            type="registry_lookup",
            severity="warning",
            description=f"No development sandbox record found for driving license '{doc_num}'.",
        ))
    elif registry_status == RegistryStatus.REVOKED:
        evidence.append(RegistryEvidence(
            type="registry_status",
            severity="critical",
            description=f"Development sandbox reports driving license '{doc_num}' as REVOKED.",
        ))
    elif registry_status == RegistryStatus.SUSPENDED:
        evidence.append(RegistryEvidence(
            type="registry_status",
            severity="critical",
            description=f"Development sandbox reports driving license '{doc_num}' as SUSPENDED.",
        ))
    elif registry_status == RegistryStatus.EXPIRED:
        evidence.append(RegistryEvidence(
            type="registry_status",
            severity="warning",
            description=f"Development sandbox reports driving license '{doc_num}' as EXPIRED.",
        ))
    elif registry_status == RegistryStatus.MISMATCH:
        mismatches = [fr.field for fr in field_results if fr.status == FieldMatchStatus.MISMATCH]
        evidence.append(RegistryEvidence(
            type="registry_mismatch",
            severity="high",
            description=(
                f"Driving license '{doc_num}' record found in sandbox, but field mismatch in: "
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

