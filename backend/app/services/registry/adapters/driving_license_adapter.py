"""
backend/app/services/registry/adapters/driving_license_adapter.py

Driving License Registry Adapter.

Translates normalized Driving License session data into a RegistryVerificationRequest
for the Driving License registry provider.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.schemas.registry import (
    DocumentFieldSource,
    FieldProvenance,
    RegistryVerificationRequest,
)
from app.services.documents.driving_license.dl_field_normalizer import (
    normalize_dl_date,
    normalize_license_number,
)
from app.services.registry.normalizers import (
    normalize_date,
    normalize_name,
)

logger = logging.getLogger(__name__)


class DrivingLicenseRegistryAdapter:
    """
    Translates Driving License session data into a normalized RegistryVerificationRequest.
    """

    def build_request(
        self,
        verification_id: str,
        session_data: Dict[str, Any],
    ) -> RegistryVerificationRequest:
        """
        Build a RegistryVerificationRequest from Driving License session data.
        """
        doc_type = "driving_license"

        # Document number is the driving license number
        doc_num = _build_provenance(
            value=session_data.get("document_number") or session_data.get("license_number"),
            source_key="document_number_source",
            session_data=session_data,
            default_source=DocumentFieldSource.VIZ,
            normalizer=normalize_license_number,
        )

        name = _build_provenance(
            value=session_data.get("name"),
            source_key="name_source",
            session_data=session_data,
            default_source=DocumentFieldSource.VIZ,
            normalizer=normalize_name,
        )

        dob = _build_provenance(
            value=session_data.get("date_of_birth") or session_data.get("dob"),
            source_key="dob_source",
            session_data=session_data,
            default_source=DocumentFieldSource.VIZ,
            normalizer=normalize_dl_date,
        )

        expiry = _build_provenance(
            value=session_data.get("expiry_date") or session_data.get("valid_to"),
            source_key="expiry_source",
            session_data=session_data,
            default_source=DocumentFieldSource.VIZ,
            normalizer=normalize_dl_date,
        )

        authority = _build_provenance(
            value=session_data.get("issuing_authority"),
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
            expiry_date=expiry,
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
