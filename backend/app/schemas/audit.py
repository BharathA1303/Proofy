"""
backend/app/schemas/audit.py

Domain schemas for Blockchain / Immutable Audit Ledger.
Defines immutable blocks, audit events, integrity verification responses,
and officer decision models.
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BlockchainEventType(str, Enum):
    GENESIS = "GENESIS"
    CASE_CREATED = "CASE_CREATED"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    OCR_COMPLETED = "OCR_COMPLETED"
    VALIDATION_COMPLETED = "VALIDATION_COMPLETED"
    FORENSICS_COMPLETED = "FORENSICS_COMPLETED"
    BIOMETRIC_COMPLETED = "BIOMETRIC_COMPLETED"
    REGISTRY_COMPLETED = "REGISTRY_COMPLETED"
    CROSS_DOCUMENT_EVALUATED = "CROSS_DOCUMENT_EVALUATED"
    RISK_ASSESSMENT_COMPLETED = "RISK_ASSESSMENT_COMPLETED"
    OFFICER_REVIEWED = "OFFICER_REVIEWED"
    EVIDENCE_ANCHORED = "EVIDENCE_ANCHORED"


class OfficerDecisionType(str, Enum):
    ADMIT = "ADMIT"
    CLEAR_ADMIT = "CLEAR_ADMIT"
    REFER_TO_SECONDARY = "REFER_TO_SECONDARY"
    REFUSE_ENTRY = "REFUSE_ENTRY"
    REQUEST_ADDITIONAL_DOCS = "REQUEST_ADDITIONAL_DOCS"
    REQUEST_ADDITIONAL_DOCUMENTS = "REQUEST_ADDITIONAL_DOCUMENTS"


class BlockchainBlock(BaseModel):
    """
    Immutable ledger block anchoring an audit milestone or evidence digest.
    Contains ZERO sensitive PII or raw biometrics.
    """
    block_index: int = Field(..., description="Monotonically increasing index (0 = Genesis)")
    previous_hash: str = Field(..., description="SHA-256 hash of previous block in chain")
    block_hash: str = Field(..., description="SHA-256 cryptographic digest of current block contents")
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp of block creation")
    target_id: str = Field(..., description="Target verification_id or case_id")
    event_type: str = Field(..., description="Lifecycle event milestone")
    evidence_hash: str = Field(..., description="SHA-256 digest of canonical evidence package or event payload")
    record_version: str = Field(default="1.0.0", description="Block payload structure version")
    system_version: str = Field(default="1.0.0-phase12", description="Application version at emission")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Non-sensitive operational telemetry")

    @property
    def payload(self) -> Dict[str, Any]:
        return self.metadata


class OfficerDecisionRequest(BaseModel):
    """Request payload for recording an authorized officer's official determination."""
    decision: OfficerDecisionType = Field(..., description="Operational decision")
    officer_id: str = Field(..., min_length=2, description="Authorized officer identifier / badge number")
    reason: Optional[str] = Field(default=None, description="Primary operational reason")
    notes: Optional[str] = Field(default=None, description="Operational justification or rationale")


class OfficerDecisionResponse(BaseModel):
    """Response returned when an officer decision is recorded on-chain."""
    target_id: str
    decision: str
    officer_id: str
    reason: Optional[str] = None
    notes: Optional[str] = None
    timestamp: float
    block_index: int
    block_hash: str
    event_type: str = "OFFICER_REVIEWED"
    status: str = "RECORDED"
    payload: Dict[str, Any] = Field(default_factory=dict)


class IntegrityVerificationResponse(BaseModel):
    """Result of cryptographic integrity verification comparing stored evidence against blockchain hashes."""
    target_id: str
    integrity_status: str = Field(..., description="'VALID' | 'INTEGRITY_FAILURE'")
    chain_valid: bool = Field(..., description="True if hash-chain sequence is intact and uncorrupted")
    events_verified: int = Field(..., description="Number of anchored lifecycle events verified")
    chain_length: int = Field(..., description="Total blocks anchored for target")
    calculated_evidence_hash: Optional[str] = None
    anchored_evidence_hash: Optional[str] = None
    details: str = Field(..., description="Audit outcome explanation")
    message: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        if self.message is None:
            self.message = self.details


class AuditChainResponse(BaseModel):
    """Response listing the chronological immutable audit blocks for a target."""
    target_id: str
    ledger_name: str = "LOCAL DEVELOPMENT LEDGER"
    source_type: str = "development_sandbox"
    ledger_type: str = "development_sandbox"
    chain_valid: bool
    total_blocks: int
    blocks: List[BlockchainBlock]
