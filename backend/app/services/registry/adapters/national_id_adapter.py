"""
backend/app/services/registry/adapters/national_id_adapter.py

National ID Registry Adapter.
Translates normalized National ID session data into a RegistryVerificationRequest
for the National ID registry provider.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.schemas.registry import (
    DocumentFieldSource,
    FieldProvenance,
    RegistryVerificationRequest,
)
from app.services.documents.national_id.national_id_field_normalizer import (
    normalize_dob_or_yob,
    normalize_name,
)
from app.services.documents.national_id.national_id_identifier_validator import (
    normalize_national_id,
)

logger = logging.getLogger(__name__)


class NationalIdRegistryAdapter:
    """
    Translates National ID session data into a normalized RegistryVerificationRequest.
    """

    def build_request(
        self,
        verification_id: str,
        session_data: Dict[str, Any],
    ) -> RegistryVerificationRequest:
        """
        Build a RegistryVerificationRequest from National ID session data.
        """
        doc_type = "national_id"

        raw_id = (
            session_data.get("identity_number")
            or session_data.get("document_number")
            or session_data.get("docNumber")
        )

        doc_num = _build_provenance(
            value=raw_id,
            source_key="identity_number_source",
            session_data=session_data,
            default_source=DocumentFieldSource.VIZ,
            normalizer=lambda v: normalize_national_id(v)[0] or v,
        )

        name = _build_provenance(
            value=session_data.get("name"),
            source_key="name_source",
            session_data=session_data,
            default_source=DocumentFieldSource.VIZ,
            normalizer=normalize_name,
        )

        # Date of birth or Year of birth
        dob_val = session_data.get("date_of_birth") or session_data.get("dob")
        yob_val = session_data.get("year_of_birth")
        date_raw = dob_val or (str(yob_val) if yob_val else None)

        dob = _build_provenance(
            value=date_raw,
            source_key="dob_source",
            session_data=session_data,
            default_source=DocumentFieldSource.VIZ,
            normalizer=lambda v: normalize_dob_or_yob(v).get("date_of_birth") or str(normalize_dob_or_yob(v).get("year_of_birth") or v),
        )

        authority = _build_provenance(
            value=session_data.get("issuing_authority") or "Unique Identification Authority of India",
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
            expiry_date=None,  # Indian National ID reference profile does not define an expiry date
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
