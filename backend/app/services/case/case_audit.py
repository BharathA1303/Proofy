"""
backend/app/services/case/case_audit.py

Structured audit logging for Verification Case events.
Ensures traceability of all multi-document lifecycle changes.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class CaseEventType(str, Enum):
    CASE_CREATED = "CASE_CREATED"
    DOCUMENT_ADDED = "DOCUMENT_ADDED"
    DOCUMENT_PROCESSED = "DOCUMENT_PROCESSED"
    DOCUMENT_REPLACED = "DOCUMENT_REPLACED"
    DOCUMENT_REMOVED = "DOCUMENT_REMOVED"
    RELATIONSHIP_EVALUATED = "RELATIONSHIP_EVALUATED"
    RELATIONSHIP_CHANGED = "RELATIONSHIP_CHANGED"
    CROSS_DOCUMENT_ANALYSIS_COMPLETED = "CROSS_DOCUMENT_ANALYSIS_COMPLETED"
    CASE_RISK_RECALCULATED = "CASE_RISK_RECALCULATED"


@dataclass
class CaseAuditEvent:
    event_id: str
    case_id: str
    event_type: str
    timestamp: float
    document_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "case_id": self.case_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "document_id": self.document_id,
            "details": self.details,
        }


def create_audit_event(
    case_id: str,
    event_type: CaseEventType | str,
    document_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> CaseAuditEvent:
    ev_type = event_type.value if isinstance(event_type, CaseEventType) else str(event_type)
    return CaseAuditEvent(
        event_id=f"EVT-{uuid.uuid4().hex[:8].upper()}",
        case_id=case_id,
        event_type=ev_type,
        timestamp=time.time(),
        document_id=document_id,
        details=details or {},
    )
