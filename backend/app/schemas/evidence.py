"""
backend/app/schemas/evidence.py

Unified Normalized Evidence Model for the AI-Based Fake Identity & Document Screening System.
Provides a standardized schema for all evidence generated across M1–M6, cross-document analysis,
and case management.
"""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EvidenceModule(str, Enum):
    OCR = "ocr"
    VALIDATION = "validation"
    FORENSICS = "forensics"
    BIOMETRICS = "biometrics"
    REGISTRY = "registry"
    RISK = "risk"
    CROSS_DOCUMENT = "cross_document"
    CASE = "case"


class EvidenceStatus(str, Enum):
    VALID = "valid"
    SUSPICIOUS = "suspicious"
    MISMATCH = "mismatch"
    WARNING = "warning"
    INFO = "info"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class EvidenceSeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NormalizedEvidenceItem(BaseModel):
    """
    Standardized, canonical evidence unit across all platform modules.
    Ensures complete provenance, traceability, and cryptographic hashability.
    """
    evidence_id: str = Field(default_factory=lambda: f"EV-{uuid.uuid4().hex[:8].upper()}")
    case_id: Optional[str] = Field(default=None, description="Associated multi-document case ID")
    document_id: str = Field(..., description="Target document ID")
    document_type: str = Field(..., description="Document profile key (e.g., passport, visa, border_permit)")
    module: EvidenceModule = Field(..., description="Generating verification module")
    signal_type: str = Field(..., description="Unique signal key (e.g., ela_anomaly, passport_binding_mismatch)")
    status: EvidenceStatus = Field(..., description="Normalized evaluation outcome")
    severity: EvidenceSeverity = Field(default=EvidenceSeverity.INFO, description="Risk severity tier")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Model/algorithm confidence score")
    description: str = Field(..., description="Human-readable explanation of the finding")
    source: str = Field(default="automated_analysis", description="Analysis origin or algorithm name")
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp of evidence emission")
    module_version: str = Field(default="1.0.0", description="Generating module release version")
    model_version: Optional[str] = Field(default=None, description="Underlying ML model version if applicable")
    provenance: Dict[str, Any] = Field(default_factory=dict, description="Detailed coordinates, field origins, or metadata")

    def to_canonical_dict(self) -> Dict[str, Any]:
        """Produce deterministically sorted dict for cryptographic hashing (excluding volatile fields)."""
        return {
            "evidence_id": self.evidence_id,
            "case_id": self.case_id or "",
            "document_id": self.document_id,
            "document_type": self.document_type,
            "module": self.module.value if hasattr(self.module, "value") else str(self.module),
            "signal_type": self.signal_type,
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "severity": self.severity.value if hasattr(self.severity, "value") else str(self.severity),
            "confidence": round(self.confidence, 4),
            "description": self.description,
            "source": self.source,
            "module_version": self.module_version,
            "model_version": self.model_version or "",
        }


class EvidencePackage(BaseModel):
    """Container grouping normalized evidence items for a document or verification case."""
    target_id: str = Field(..., description="verification_id or case_id")
    target_type: str = Field(default="document", description="'document' or 'case'")
    timestamp: float = Field(default_factory=time.time)
    items: List[NormalizedEvidenceItem] = Field(default_factory=list)
    system_version: str = Field(default="1.0.0-phase12")

    def to_canonical_dict(self) -> Dict[str, Any]:
        """Sorted, canonical dict representation used for SHA-256 evidence hashing."""
        return {
            "target_id": self.target_id,
            "target_type": self.target_type,
            "system_version": self.system_version,
            "items": [item.to_canonical_dict() for item in sorted(self.items, key=lambda i: i.evidence_id)],
        }
