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
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
#  Enumerations
# ──────────────────────────────────────────────

class RegistryStatus(str, Enum):
    """Explicit outcome of a registry verification attempt."""
    ACTIVE               = "ACTIVE"
    MATCHED              = "MATCHED"
    NOT_FOUND            = "NOT_FOUND"
    MISMATCH             = "MISMATCH"
    EXPIRED              = "EXPIRED"
    REVOKED              = "REVOKED"
    SUSPENDED            = "SUSPENDED"
    INVALID              = "INVALID"
    AMBIGUOUS            = "AMBIGUOUS"
    UNAVAILABLE          = "UNAVAILABLE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    TIMEOUT              = "TIMEOUT"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    UNAUTHORIZED         = "UNAUTHORIZED"
    RATE_LIMITED         = "RATE_LIMITED"
    INVALID_REQUEST      = "INVALID_REQUEST"
    PROVIDER_ERROR       = "PROVIDER_ERROR"
    ERROR                = "ERROR"
    NOT_CONFIGURED       = "NOT_CONFIGURED"
    LIVE_PROVIDER_NOT_CONFIGURED = "LIVE_PROVIDER_NOT_CONFIGURED"
    PROVIDER_RESPONSE_INVALID = "PROVIDER_RESPONSE_INVALID"
    INCONCLUSIVE         = "INCONCLUSIVE"


class FieldMatchStatus(str, Enum):
    """Result of comparing a single identity field between document and registry."""
    MATCH                = "MATCH"
    PARTIAL_MATCH        = "PARTIAL_MATCH"
    MISMATCH             = "MISMATCH"
    MISSING_IN_REGISTRY  = "MISSING_IN_REGISTRY"
    MISSING_IN_DOCUMENT  = "MISSING_IN_DOCUMENT"
    NOT_COMPARED         = "NOT_COMPARED"
    AMBIGUOUS            = "AMBIGUOUS"
    UNAVAILABLE          = "UNAVAILABLE"


class ProviderSourceType(str, Enum):
    """Identifies the nature of the registry provider.
    MUST be visible in all responses so UI never misleads the officer."""
    DEVELOPMENT_MOCK             = "development_mock"
    SANDBOX                      = "sandbox"
    AUTHORIZED_EXTERNAL          = "authorized_external"
    AUTHORIZED_EXTERNAL_PROVIDER = "authorized_external_provider"
    UNAVAILABLE                  = "unavailable"
    NOT_CONFIGURED               = "not_configured"


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
    valid_from: Optional[FieldProvenance] = None
    issuing_authority: Optional[FieldProvenance] = None
    gender: Optional[FieldProvenance] = None
    vehicle_classes: Optional[FieldProvenance] = None
    state: Optional[FieldProvenance] = None
    blood_group: Optional[FieldProvenance] = None
    client_metadata: Optional[Dict[str, Any]] = None
    query_hash: Optional[str] = None


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
    valid_from: Optional[str] = None
    issuing_authority: Optional[str] = None
    gender: Optional[str] = None
    vehicle_classes: Optional[Union[List[str], str]] = None
    state: Optional[str] = None
    blood_group: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

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
    comparison_method: Optional[str] = Field(
        default=None,
        description="Method used for comparison (e.g. 'strict_equality', 'token_normalized', 'cov_taxonomy')",
    )
    source_document: Optional[str] = Field(default=None, description="Raw document extracted value")
    source_registry: Optional[str] = Field(default=None, description="Raw registry record value")
    normalized_document: Optional[str] = Field(default=None, description="Normalized document value")
    normalized_registry: Optional[str] = Field(default=None, description="Normalized registry value")
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

    provider_type: Optional[str] = Field(
        default=None,
        description="Type of registry provider (e.g. 'development_mock', 'authorized_external')",
    )

    query_hash: Optional[str] = Field(
        default=None,
        description="Cryptographic SHA-256 hash of query parameters (privacy-preserving reference)",
    )

    freshness: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Cache freshness telemetry: cached, retrieved_at, ttl_seconds, is_fresh",
    )

    profile_version: Optional[str] = Field(
        default=None,
        description="Document profile version used for field corroboration rules",
    )

    field_comparisons: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Structured field comparison summaries",
    )

    def to_evidence_dict(self) -> Dict[str, Any]:
        """Serialize evidence dictionary for audit trail, M6 risk engine, and blockchain ledger."""
        src_t = self.provider_metadata.source_type
        p_type = src_t.value if hasattr(src_t, "value") else str(src_t)
        return {
            "verification_id": self.verification_id,
            "document_type": self.document_type,
            "provider": self.registry.get("provider"),
            "provider_type": p_type,
            "lookup_status": self.registry.get("status"),
            "record_found": self.registry.get("record_found", False),
            "registry_document_status": self.registry.get("registry_document_status"),
            "query_hash": self.query_hash,
            "field_results": [f.model_dump() for f in self.field_results],
            "evidence": [e.model_dump() for e in self.evidence],
            "freshness": self.freshness or {},
            "profile_version": self.profile_version or "default",
        }
