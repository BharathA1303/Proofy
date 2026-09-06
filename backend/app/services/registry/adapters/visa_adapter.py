"""
backend/app/services/registry/adapters/visa_adapter.py

Visa Registry Adapter.

Translates normalized Visa session data into a RegistryVerificationRequest
for the Visa registry provider.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.schemas.registry import (
    DocumentFieldSource,
    FieldProvenance,
    RegistryVerificationRequest,
)
from app.services.registry.normalizers import (
    normalize_date,
    normalize_document_number,
    normalize_name,
    normalize_nationality,
)

logger = logging.getLogger(__name__)


class VisaRegistryAdapter:
    """
    Translates Visa session data into a normalized RegistryVerificationRequest.
    """

    def build_request(
        self,
        verification_id: str,
        session_data: Dict[str, Any],
    ) -> RegistryVerificationRequest:
        """
        Build a RegistryVerificationRequest from Visa session data.
        """
        doc_type = "visa"

        # Document number is the visa number
        doc_num = _build_provenance(
            value=session_data.get("document_number"),
            source_key="document_number_source",
            session_data=session_data,
            default_source=DocumentFieldSource.VIZ,
            normalizer=normalize_document_number,
        )

        name = _build_provenance(
            value=session_data.get("name"),
            source_key="name_source",
            session_data=session_data,
            default_source=DocumentFieldSource.VIZ,
            normalizer=normalize_name,
        )

        dob = _build_provenance(
            value=session_data.get("date_of_birth"),
            source_key="dob_source",
            session_data=session_data,
            default_source=DocumentFieldSource.VIZ,
            normalizer=normalize_date,
        )

        nationality = _build_provenance(
            value=session_data.get("nationality"),
            source_key="nationality_source",
            session_data=session_data,
            default_source=DocumentFieldSource.VIZ,
            normalizer=normalize_nationality,
        )

        expiry = _build_provenance(
            value=session_data.get("expiry_date"),
            source_key="expiry_source",
            session_data=session_data,
            default_source=DocumentFieldSource.VIZ,
            normalizer=normalize_date,
        )

        authority = _build_provenance(
            value=session_data.get("issuing_authority"),
            source_key="authority_source",
            session_data=session_data,
            default_source=DocumentFieldSource.VIZ,
            normalizer=None,
        )

        # Additional metadata for visa specific checks
        extra: Dict[str, Any] = {}
        if session_data.get("passport_number"):
            extra["passport_number"] = normalize_document_number(session_data["passport_number"])
        if session_data.get("visa_type"):
            extra["visa_type"] = session_data["visa_type"]
        if session_data.get("entries"):
            extra["entries"] = session_data["entries"]

        return RegistryVerificationRequest(
            verification_id=verification_id,
            document_type=doc_type,
            document_number=doc_num,
            name=name,
            date_of_birth=dob,
            nationality=nationality,
            expiry_date=expiry,
            issuing_authority=authority,
            extra=extra if extra else None,
        )


def _build_provenance(
    value: Optional[str],
    source_key: str,
    session_data: Dict[str, Any],
    default_source: DocumentFieldSource,
    normalizer=None,
) -> Optional[FieldProvenance]:
    """Build a FieldProvenance instance if value is present."""
    if not value or not str(value).strip():
        return None

    raw = str(value).strip()
    norm = normalizer(raw) if normalizer else raw
    src_str = session_data.get(source_key, default_source.value)

    try:
        source_enum = DocumentFieldSource(src_str)
    except (ValueError, KeyError):
        source_enum = default_source

    return FieldProvenance(
        value=norm,
        raw_value=raw,
        source=source_enum,
    )
