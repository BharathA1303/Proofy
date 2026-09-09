"""
backend/app/services/registry/providers/mock_voter_id.py

Development Mock Registry Provider for Voter ID / EPIC Cards.
Emulates an Election Commission of India voter roll lookup.

DEVELOPMENT USE ONLY — Not a real ECI voter database.
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


class _VoterIdRecordProxy(dict):
    def __getitem__(self, key: str):
        res = government_registry_db.lookup_document("voter_id", key)
        if not res:
            raise KeyError(key)
        return res

    def __contains__(self, key: object):
        if not isinstance(key, str):
            return False
        return government_registry_db.lookup_document("voter_id", key) is not None

    def get(self, key: str, default=None):
        res = government_registry_db.lookup_document("voter_id", key)
        return res if res is not None else default

    def keys(self):
        return government_registry_db.get_all_records_for_type("voter_id").keys()


_MOCK_VOTER_RECORDS = _VoterIdRecordProxy()


class MockVoterIdRegistryProvider(RegistryProvider):
    """Mock Voter ID registry provider for development and testing."""
    _PROVIDER_ID     = "mock_voter_id_registry"
    _SUPPORTED_TYPES = {"voter_id", "voterid", "epic", "voter"}

    def __init__(self) -> None:
        self._available = True

    @property
    def provider_id(self) -> str:
        return self._PROVIDER_ID

    def initialize(self) -> None:
        logger.info("MockVoterIdRegistryProvider initialized: %s (DEVELOPMENT MOCK)", self._PROVIDER_ID)

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
            details="Development mock provider for Voter ID / EPIC. NOT a real ECI voter roll.",
        )

    def verify(self, request: RegistryVerificationRequest) -> RegistryVerificationResponse:
        t_start = time.perf_counter()
        time.sleep(_MOCK_LATENCY_MS / 1000.0)

        doc_num_prov = request.document_number
        doc_num      = doc_num_prov.value if doc_num_prov else None
        lookup_key   = (doc_num or "").strip().upper()
        t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        logger.info("MockVoterIdRegistry lookup: id=%s epic=%s", request.verification_id, lookup_key)

        if not lookup_key or lookup_key not in _MOCK_VOTER_RECORDS:
            return self._build_response(
                request=request,
                registry_status=RegistryStatus.NOT_FOUND,
                record=None,
                field_results=[],
                evidence=[RegistryEvidence(
                    type="registry_lookup", severity="info",
                    description=f"No development mock record found for Voter ID / EPIC '{lookup_key}'.",
                )],
                response_time_ms=t_elapsed_ms,
            )

        raw_record = _MOCK_VOTER_RECORDS[lookup_key]
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

        evidence = _build_voter_evidence(status, field_results, lookup_key)
        if raw_record.get("is_blacklisted"):
            evidence.insert(0, RegistryEvidence(
                type="watchlist_hit", severity="critical",
                description=f"GOVERNMENT WATCHLIST ALERT: {raw_record.get('watchlist_reason', 'Voter ID suspended/revoked.')}",
            ))

        t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        return self._build_response(request, status, reg_record, field_results, evidence, t_elapsed_ms)

    def _build_response(self, request, registry_status, record, field_results, evidence, response_time_ms):
        return RegistryVerificationResponse(
            verification_id=request.verification_id,
            document_type=request.document_type,
            registry={
                "provider": self._PROVIDER_ID,
                "status": registry_status.value,
                "record_found": record is not None,
                "registry_document_status": (record.registry_document_status if record else None),
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
                "disclaimer": "DEVELOPMENT MOCK DATA — not a real ECI voter roll result.",
            },
        )


def _build_voter_evidence(status, field_results, epic_num):
    evidence = []
    if status == RegistryStatus.MATCHED:
        evidence.append(RegistryEvidence(type="registry_record", severity="info",
            description=f"Development sandbox voter record located for EPIC '{epic_num}' and identity fields matched."))
    elif status == RegistryStatus.NOT_FOUND:
        evidence.append(RegistryEvidence(type="registry_lookup", severity="warning",
            description=f"No development sandbox voter record found for EPIC '{epic_num}'."))
    elif status == RegistryStatus.REVOKED:
        evidence.append(RegistryEvidence(type="registry_status", severity="critical",
            description=f"Development sandbox reports Voter ID '{epic_num}' as REVOKED."))
    elif status == RegistryStatus.MISMATCH:
        mismatches = [fr.field for fr in field_results if fr.status == FieldMatchStatus.MISMATCH]
        evidence.append(RegistryEvidence(type="registry_mismatch", severity="high",
            description=f"Voter ID '{epic_num}' found but field mismatch in: {', '.join(mismatches)}."))
    else:
        evidence.append(RegistryEvidence(type="registry_status", severity="info",
            description=f"Registry status: {status.value}."))
    return evidence
