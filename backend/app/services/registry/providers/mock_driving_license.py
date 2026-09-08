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
from app.services.registry.db.registry_db import government_registry_db

logger = logging.getLogger(__name__)

_MOCK_LATENCY_MS = 50.0

class _DLRecordProxy(dict):
    """Proxy providing backward compatibility by decrypting SQLite records on demand."""
    def __getitem__(self, key: str):
        res = government_registry_db.lookup_document("driving_license", key)
        if not res:
            raise KeyError(key)
        return res

    def __contains__(self, key: object):
        if not isinstance(key, str):
            return False
        return government_registry_db.lookup_document("driving_license", key) is not None

    def get(self, key: str, default=None):
        res = government_registry_db.lookup_document("driving_license", key)
        return res if res is not None else default

    def keys(self):
        return government_registry_db.get_all_records_for_type("driving_license").keys()

    def values(self):
        return government_registry_db.get_all_records_for_type("driving_license").values()

    def items(self):
        return government_registry_db.get_all_records_for_type("driving_license").items()

_MOCK_DL_RECORDS = _DLRecordProxy()


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
        if raw_record.get("is_blacklisted") and reg_record.registry_document_status != "SUSPENDED":
            status = RegistryStatus.REVOKED

        evidence = _build_evidence(status, field_results, lookup_key)
        if raw_record.get("is_blacklisted"):
            evidence.insert(0, RegistryEvidence(
                type="watchlist_hit",
                severity="critical",
                description=f"GOVERNMENT WATCHLIST ALERT: {raw_record.get('watchlist_reason', 'Driving licence revoked on transport watchlist.')}",
            ))

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

