"""
backend/app/schemas/registry.py

Pydantic v2 schemas for Module 5: Registry Verification Engine.

IMPORTANT — design contract:
  - RegistryVerificationResponse NEVER contains risk_score, final_decision,
    or any verdict vocabulary ('CLEARED', 'DENIED', 'FORGED', etc.).
  - The registry is an EVIDENCE PROVIDER only. The Risk Engine (Module 6)
    combines this evidence with M1–M4 signals to produce the final decision.
  - source_type MUST be visible so the UI can distinguish
    development_mock from authorized_external providers.
  - Credentials, raw provider tokens, and internal database paths are
    never included in any response schema.

Registry status vocabulary (aligned with ICAO / border screening practice):
  MATCHED              All critical identity fields verified against registry.
  NOT_FOUND            No record found — NOT the same as INVALID or FORGED.
  MISMATCH             Record found but one or more critical fields differ.
  EXPIRED              Registry reports document as expired.
  REVOKED              Registry reports document as revoked.
  SUSPENDED            Registry reports document as suspended.
  INVALID              Registry considers the document structurally invalid.
  AMBIGUOUS            Multiple registry records match; cannot disambiguate.
  UNAVAILABLE          Provider unreachable — document cannot be checked.
  TIMEOUT              Provider call exceeded time budget.
  AUTHENTICATION_ERROR Provider rejected the request (future external providers).
  PROVIDER_ERROR       Unexpected provider-side error.
  INCONCLUSIVE         Record found but insufficient fields to determine match.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
#  Enumerations
# ──────────────────────────────────────────────

class RegistryStatus(str, Enum):
    """Explicit outcome of a registry verification attempt."""
    MATCHED              = "MATCHED"
    NOT_FOUND            = "NOT_FOUND"
    MISMATCH             = "MISMATCH"
    EXPIRED              = "EXPIRED"
    REVOKED              = "REVOKED"
    SUSPENDED            = "SUSPENDED"
    INVALID              = "INVALID"
    AMBIGUOUS            = "AMBIGUOUS"
    UNAVAILABLE          = "UNAVAILABLE"
    TIMEOUT              = "TIMEOUT"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    PROVIDER_ERROR       = "PROVIDER_ERROR"
    INCONCLUSIVE         = "INCONCLUSIVE"


class FieldMatchStatus(str, Enum):
    """Result of comparing a single identity field between document and registry."""
    MATCH              = "MATCH"
    MISMATCH           = "MISMATCH"
    MISSING_IN_REGISTRY  = "MISSING_IN_REGISTRY"
    MISSING_IN_DOCUMENT  = "MISSING_IN_DOCUMENT"
    NOT_COMPARED         = "NOT_COMPARED"


class ProviderSourceType(str, Enum):
    """Identifies the nature of the registry provider.
    MUST be visible in all responses so UI never misleads the officer."""
    DEVELOPMENT_MOCK    = "development_mock"
    SANDBOX             = "sandbox"
    AUTHORIZED_EXTERNAL = "authorized_external"


class DocumentFieldSource(str, Enum):
    """Tracks which zone of the document a field was extracted from."""
    MRZ    = "mrz"
    VIZ    = "viz"
    PARSED = "parsed"
    NONE   = "none"


# ──────────────────────────────────────────────
#  Field provenance
# ──────────────────────────────────────────────

class FieldProvenance(BaseModel):
    """Documents exactly where each identity field came from."""
    value: Optional[str] = Field(default=None, description="Normalized field value")
    source: DocumentFieldSource = Field(
        default=DocumentFieldSource.NONE,
        description="Zone from which value was extracted (mrz | viz | parsed | none)",
    )


# ──────────────────────────────────────────────
#  Request
# ──────────────────────────────────────────────

class RegistryVerificationRequest(BaseModel):
    """
    Normalized request sent to the registry provider.

    All fields are pre-normalized by the adapter (uppercase, stripped, etc.).
    Fields not available in the document session are omitted (None).

    SECURITY: This object is built server-side from the session store.
    It is NEVER constructed from arbitrary client-submitted values.
    """
    verification_id: str = Field(..., description="Unique verification session ID")
    document_type: str = Field(..., description="Document type key (e.g. 'passport')")

    # Identity fields with provenance
    document_number: Optional[FieldProvenance] = None
    date_of_birth: Optional[FieldProvenance] = None
    name: Optional[FieldProvenance] = None
    nationality: Optional[FieldProvenance] = None
    expiry_date: Optional[FieldProvenance] = None
    issuing_authority: Optional[FieldProvenance] = None
    gender: Optional[FieldProvenance] = None


# ──────────────────────────────────────────────
#  Registry record (normalized from provider)
# ──────────────────────────────────────────────

class RegistryRecord(BaseModel):
    """
    Normalized registry record returned by a provider.
    Only fields relevant to identity comparison are extracted.
    Raw provider responses are NOT stored or forwarded.
    """
    document_number: Optional[str] = None
    name: Optional[str] = None
    date_of_birth: Optional[str] = None
    nationality: Optional[str] = None
    expiry_date: Optional[str] = None
    issuing_authority: Optional[str] = None
    gender: Optional[str] = None

    # Document status according to registry
    registry_document_status: str = Field(
        default="UNKNOWN",
        description="Registry-reported status: 'ACTIVE' | 'REVOKED' | 'EXPIRED' | 'SUSPENDED' | 'INVALID' | 'UNKNOWN'",
    )


# ──────────────────────────────────────────────
#  Field-level comparison results
# ──────────────────────────────────────────────

class RegistryFieldResult(BaseModel):
    """
    Evidence item for a single field comparison between document and registry.

    Example:
      field           = "document_number"
      document_value  = "T9876543"
      registry_value  = "T9876543"
      status          = "MATCH"
    """
    field: str = Field(..., description="Identity field name (e.g. 'document_number')")
    document_value: Optional[str] = Field(
        default=None, description="Value from the document/OCR session (normalized)"
    )
    registry_value: Optional[str] = Field(
        default=None, description="Value from the registry record (normalized)"
    )
    status: FieldMatchStatus = Field(..., description="Comparison outcome")
    is_critical: bool = Field(
        default=False,
        description="True if this field is part of the critical identity set for this document type",
    )
    note: Optional[str] = Field(
        default=None,
        description="Optional explanation (e.g. normalization note, mismatch detail)",
    )


# ──────────────────────────────────────────────
#  Evidence items
# ──────────────────────────────────────────────

class RegistryEvidence(BaseModel):
    """Structured evidence item for the audit trail and Risk Engine."""
    type: str = Field(..., description="Evidence type (e.g. 'registry_record', 'field_mismatch')")
    severity: str = Field(
        ...,
        description="'info' | 'warning' | 'critical'",
    )
    description: str = Field(..., description="Human-readable evidence description for officer review")


# ──────────────────────────────────────────────
#  Provider health / status
# ──────────────────────────────────────────────

class RegistryProviderStatus(BaseModel):
    """Health and availability status of a registry provider."""
    provider_id: str
    source_type: ProviderSourceType
    available: bool
    supported_document_types: List[str]
    details: Optional[str] = None


# ──────────────────────────────────────────────
#  API Request body
# ──────────────────────────────────────────────

class RegistryVerifyRequest(BaseModel):
    """Request body for POST /api/v1/verification/registry.

    The server retrieves identity data from the server-side session store.
    The client only provides the session reference (verification_id).
    """
    verification_id: str = Field(..., description="Unique verification session ID from Module 1")
    document_type: str = Field(
        default="passport",
        description="Document type key (e.g. 'passport')",
    )


# ──────────────────────────────────────────────
#  API Response
# ──────────────────────────────────────────────

class RegistryProviderMetadata(BaseModel):
    """Non-sensitive metadata about the registry provider that was called."""
    provider_id: str
    source_type: ProviderSourceType = Field(
        ...,
        description=(
            "MUST be visible in response. "
            "'development_mock' means simulated sandbox data — "
            "NOT a real government registry result."
        ),
    )
    response_time_ms: Optional[float] = None


class RegistryVerificationResponse(BaseModel):
    """
    Response for POST /api/v1/verification/registry.

    Module 5 provides registry EVIDENCE only.
    This response MUST NOT contain:
      - risk_score
      - final_decision / overall_verdict
      - 'CLEARED', 'DENIED', 'SAFE', 'DANGEROUS', 'FORGERY CONFIRMED'

    Those belong to Module 6 (Risk Engine).
    """
    verification_id: str
    document_type: str

    registry: Dict[str, Any] = Field(
        ...,
        description="High-level registry summary {provider, status, record_found}",
    )

    field_results: List[RegistryFieldResult] = Field(
        default_factory=list,
        description="Per-field comparison evidence between document and registry",
    )

    evidence: List[RegistryEvidence] = Field(
        default_factory=list,
        description="Structured evidence items for audit trail and Risk Engine",
    )

    provider_metadata: RegistryProviderMetadata = Field(
        ...,
        description="Non-sensitive provider telemetry. source_type is always visible.",
    )

    audit: Dict[str, Any] = Field(
        default_factory=dict,
        description="Audit trail: timestamps, provider id, processing duration",
    )
