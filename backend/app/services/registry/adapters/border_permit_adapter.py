"""
backend/app/services/registry/adapters/border_permit_adapter.py

Border Permit Registry Adapter.
Translates normalized Border Permit session data into a RegistryVerificationRequest
for the Border Permit registry provider.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.schemas.registry import (
    DocumentFieldSource,
    FieldProvenance,
    RegistryVerificationRequest,
)
from app.services.documents.border_permit.border_permit_field_normalizer import (
    normalize_border_date,
    normalize_holder_name,
    normalize_permit_number,
)

logger = logging.getLogger(__name__)


class BorderPermitRegistryAdapter:
    """
    Translates Border Permit session data into a normalized RegistryVerificationRequest.
    """

    def build_request(
        self,
        verification_id: str,
        session_data: Dict[str, Any],
    ) -> RegistryVerificationRequest:
        doc_type = "border_permit"

        raw_id = (
            session_data.get("permit_number")
            or session_data.get("permitNumber")
            or session_data.get("document_number")
            or session_data.get("docNumber")
        )

        doc_num = _build_provenance(
            value=raw_id,
            source_key="permit_number_source",
            session_data=session_data,
            default_source=DocumentFieldSource.VIZ,
            normalizer=lambda v: normalize_permit_number(v)[0] or v,
        )

        name = _build_provenance(
            value=session_data.get("name"),
            source_key="name_source",
            session_data=session_data,
            default_source=DocumentFieldSource.VIZ,
            normalizer=normalize_holder_name,
        )

        dob = _build_provenance(
            value=session_data.get("date_of_birth") or session_data.get("dob"),
            source_key="dob_source",
            session_data=session_data,
            default_source=DocumentFieldSource.VIZ,
            normalizer=normalize_border_date,
        )

        exp = _build_provenance(
            value=session_data.get("valid_to") or session_data.get("expiry_date") or session_data.get("expiry") or session_data.get("validTo"),
            source_key="expiry_source",
            session_data=session_data,
            default_source=DocumentFieldSource.VIZ,
            normalizer=normalize_border_date,
        )

        authority = _build_provenance(
            value=session_data.get("issuing_authority") or session_data.get("authority") or "Border Management Authority",
            source_key="authority_source",
            session_data=session_data,
            default_source=DocumentFieldSource.VIZ,
            normalizer=None,
        )

        return RegistryVerificationRequest(
            verification_id=verification_id,
            document_type=doc_type,
            document_number=doc_num,
            name=name,
            date_of_birth=dob,
            nationality=None,
            expiry_date=exp,
            issuing_authority=authority,
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
    except ValueError:
        source_enum = default_source

    return FieldProvenance(
        value=norm or raw,
        source=source_enum,
    )
