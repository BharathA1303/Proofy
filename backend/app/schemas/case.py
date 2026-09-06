"""
backend/app/schemas/case.py

Pydantic v2 schemas for Verification Cases and Multi-Document Screening.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.cross_document import CrossDocumentEvidenceItem


class CaseStatus(str, Enum):
    """Lifecycle status of a verification case."""
    ACTIVE = "active"
    PROCESSING = "processing"
    READY_FOR_REVIEW = "ready_for_review"
    COMPLETED = "completed"
    ERROR = "error"


class DocumentStatus(str, Enum):
    """Lifecycle status of an individual document within a case."""
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    REMOVED = "removed"
    SUPERSEDED = "superseded"


class CaseDocumentSummary(BaseModel):
    """Summary of a document registered in a verification case."""
    document_id: str
    document_type: str
    document_revision: int = 1
    status: DocumentStatus
    verification_id: str
    uploaded_at: float
    filename: Optional[str] = None
    traveler_summary: Dict[str, Any] = Field(default_factory=dict)
    module_statuses: Dict[str, str] = Field(default_factory=dict)


class CreateCaseRequest(BaseModel):
    """Request payload for creating a new verification case."""
    case_id: Optional[str] = None
    notes: Optional[str] = None


class CaseRiskRequest(BaseModel):
    """Request payload for evaluating case-level risk."""
    case_id: str


class CaseRiskAssessment(BaseModel):
    """Composite case-level risk assessment with officer decision support."""
    risk_score: int
    risk_level: str
    officer_recommendation: str
    recommendation: Optional[str] = None
    documents_considered: List[str]
    cross_document_evidence: List[CrossDocumentEvidenceItem]
    conflict_detected: bool = False
    reasons: List[Dict[str, Any]] = Field(default_factory=list)
    conflicts: List[Dict[str, Any]] = Field(default_factory=list)
    verification_completeness: float = 1.0
    risk_config_version: str = "0.6.0"


class VerificationCaseResponse(BaseModel):
    """Full representation of a verification case."""
    case_id: str
    status: CaseStatus
    created_at: float
    updated_at: float
    documents: List[CaseDocumentSummary] = Field(default_factory=list)
    relationships: List[CrossDocumentEvidenceItem] = Field(default_factory=list)
    cross_document_evidence: List[CrossDocumentEvidenceItem] = Field(default_factory=list)
    risk_assessment: Optional[CaseRiskAssessment] = None
    notes: Optional[str] = None
    audit_events: List[Dict[str, Any]] = Field(default_factory=list)
    blockchain_audit: Optional[Dict[str, Any]] = None
