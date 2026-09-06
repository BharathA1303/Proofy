"""
backend/app/services/registry/adapters/passport_adapter.py

Passport Registry Adapter.

Translates the normalized session data (from RegistrySessionStore) into a
RegistryVerificationRequest for the Passport registry provider.

RESPONSIBILITIES:
  - Extract relevant fields from the session data dict.
  - Assign provenance (source: mrz | viz | parsed).
  - Build the RegistryVerificationRequest.

NON-RESPONSIBILITIES:
  - MRZ parsing         → belongs to Module 1 (OCR)
  - ICAO validation     → belongs to Module 2 (Document Validation)
  - No field re-parsing or re-extraction
  - No OCR or image access

PROVENANCE TRACKING:
  MRZ-sourced fields are prioritized as more reliable for registry lookup
  because the MRZ is machine-readable and checksum-validated by Module 2.
  VIZ-sourced fields are used as fallback.
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


class PassportRegistryAdapter:
    """
    Translates passport session data into a normalized RegistryVerificationRequest.

    Session data dict is expected to have keys populated from Module 1/2 output:
      - 'document_number'   (str or None)
      - 'name'              (str or None)
      - 'date_of_birth'     (str or None)
      - 'nationality'       (str or None)
      - 'expiry_date'       (str or None)
      - 'issuing_authority' (str or None)
      - 'gender'            (str or None)
      - 'name_source'       ('mrz' | 'viz' | 'parsed') — optional
      - 'dob_source'        ('mrz' | 'viz' | 'parsed') — optional
      etc.
    """

    def build_request(
        self,
        verification_id: str,
        session_data: Dict[str, Any],
    ) -> RegistryVerificationRequest:
        """
        Build a RegistryVerificationRequest from session data.

        Only includes fields that are actually available — never invents missing values.
        """
        doc_type = "passport"

        doc_num = _build_provenance(
            value=session_data.get("document_number"),
            source_key="document_number_source",
            session_data=session_data,
            default_source=DocumentFieldSource.MRZ,
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
            default_source=DocumentFieldSource.MRZ,
            normalizer=normalize_date,
        )

        nationality = _build_provenance(
            value=session_data.get("nationality"),
            source_key="nationality_source",
            session_data=session_data,
            default_source=DocumentFieldSource.MRZ,
            normalizer=normalize_nationality,
        )

        expiry = _build_provenance(
            value=session_data.get("expiry_date"),
            source_key="expiry_source",
            session_data=session_data,
            default_source=DocumentFieldSource.MRZ,
            normalizer=normalize_date,
        )

        authority = _build_provenance(
            value=session_data.get("issuing_authority"),
            source_key="authority_source",
            session_data=session_data,
            default_source=DocumentFieldSource.VIZ,
            normalizer=None,
        )

        gender = _build_provenance(
            value=session_data.get("gender"),
            source_key="gender_source",
            session_data=session_data,
            default_source=DocumentFieldSource.MRZ,
            normalizer=None,
        )

        request = RegistryVerificationRequest(
            verification_id=verification_id,
            document_type=doc_type,
            document_number=doc_num,
            date_of_birth=dob,
            name=name,
            nationality=nationality,
            expiry_date=expiry,
            issuing_authority=authority,
            gender=gender,
        )

        logger.debug(
            "PassportRegistryAdapter built request for id=%s "
            "doc_num_available=%s dob_available=%s name_available=%s",
            verification_id,
            doc_num is not None,
            dob is not None,
            name is not None,
        )

        return request


def _build_provenance(
    value: Optional[str],
    source_key: str,
    session_data: Dict[str, Any],
    default_source: DocumentFieldSource,
    normalizer,
) -> Optional[FieldProvenance]:
    """
    Build a FieldProvenance object for a single field.
    Returns None if the value is not available.
    """
    if not value or not value.strip():
        return None

    # Apply normalization if provided
    normalized = normalizer(value) if normalizer else value.strip().upper()

    if not normalized:
        return None

    # Determine provenance source
    raw_source = session_data.get(source_key, "").lower()
    if raw_source == "mrz":
        source = DocumentFieldSource.MRZ
    elif raw_source == "viz":
        source = DocumentFieldSource.VIZ
    elif raw_source == "parsed":
        source = DocumentFieldSource.PARSED
    else:
        source = default_source

    return FieldProvenance(value=normalized, source=source)
