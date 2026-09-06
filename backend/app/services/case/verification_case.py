"""
backend/app/services/case/verification_case.py

Domain models for Multi-Document Verification Cases.
Encapsulates documents, relationship states, and case-level lifecycle.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.schemas.case import CaseStatus, DocumentStatus
from app.schemas.cross_document import CrossDocumentEvidenceItem
from app.services.case.case_audit import CaseAuditEvent, CaseEventType, create_audit_event
from app.services.risk.risk_evidence import RiskEvidenceItem
from app.services.audit.ledger import blockchain_ledger


@dataclass
class CaseDocument:
    """An individual document credential inside a verification case."""
    document_id: str
    document_type: str
    verification_id: str
    status: DocumentStatus = DocumentStatus.UPLOADED
    document_revision: int = 1
    uploaded_at: float = field(default_factory=time.time)
    filename: Optional[str] = None
    traveler_data: Dict[str, Any] = field(default_factory=dict)
    module_statuses: Dict[str, str] = field(default_factory=dict)

    def to_summary_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "document_type": self.document_type,
            "document_revision": self.document_revision,
            "status": self.status.value,
            "verification_id": self.verification_id,
            "uploaded_at": self.uploaded_at,
            "filename": self.filename,
            "traveler_summary": self.traveler_data,
            "module_statuses": self.module_statuses,
        }


@dataclass
class VerificationCase:
    """The master screening case tracking multiple identity documents."""
    case_id: str
    status: CaseStatus = CaseStatus.ACTIVE
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    documents: Dict[str, CaseDocument] = field(default_factory=dict)
    relationships: List[CrossDocumentEvidenceItem] = field(default_factory=list)
    cross_document_evidence: List[RiskEvidenceItem] = field(default_factory=list)
    risk_assessment: Optional[Dict[str, Any]] = None
    audit_trail: List[CaseAuditEvent] = field(default_factory=list)
    active_document_id: Optional[str] = None
    notes: Optional[str] = None

    def add_document(self, doc: CaseDocument) -> None:
        self.documents[doc.document_id] = doc
        self.active_document_id = doc.document_id
        self.updated_at = time.time()
        self.record_event(
            CaseEventType.DOCUMENT_ADDED,
            document_id=doc.document_id,
            details={"document_type": doc.document_type, "filename": doc.filename},
        )

    def get_document(self, document_id: str) -> Optional[CaseDocument]:
        return self.documents.get(document_id)

    def get_active_documents(self) -> List[CaseDocument]:
        return [
            doc for doc in self.documents.values()
            if doc.status not in (DocumentStatus.REMOVED, DocumentStatus.SUPERSEDED)
        ]

    def has_document_type(self, document_type: str) -> bool:
        norm = document_type.strip().lower()
        return any(
            doc.document_type.strip().lower() == norm
            for doc in self.get_active_documents()
        )

    def get_document_by_type(self, document_type: str) -> Optional[CaseDocument]:
        norm = document_type.strip().lower()
        for doc in self.get_active_documents():
            if doc.document_type.strip().lower() == norm:
                return doc
        return None

    def supersede_document_type(self, document_type: str) -> Optional[CaseDocument]:
        existing = self.get_document_by_type(document_type)
        if existing:
            existing.status = DocumentStatus.SUPERSEDED
            self.invalidate_relationships_for_document(existing.document_id)
            self.updated_at = time.time()
            self.record_event(
                CaseEventType.DOCUMENT_REPLACED,
                document_id=existing.document_id,
                details={"document_type": document_type, "revision": existing.document_revision},
            )
        return existing

    def remove_document(self, document_id: str) -> Optional[CaseDocument]:
        doc = self.documents.get(document_id)
        if doc:
            doc.status = DocumentStatus.REMOVED
            self.invalidate_relationships_for_document(document_id)
            self.updated_at = time.time()
            self.record_event(
                CaseEventType.DOCUMENT_REMOVED,
                document_id=document_id,
                details={"document_type": doc.document_type},
            )
            # If the removed document was active, reset active_document_id
            active_docs = self.get_active_documents()
            self.active_document_id = active_docs[0].document_id if active_docs else None
        return doc

    def invalidate_relationships_for_document(self, document_id: str) -> None:
        """Purge any relationship and risk evidence referencing document_id."""
        initial_count = len(self.relationships)
        self.relationships = [
            rel for rel in self.relationships
            if rel.source_document.document_id != document_id
            and rel.target_document.document_id != document_id
        ]
        self.cross_document_evidence = [
            ev for ev in self.cross_document_evidence
            if ev.provenance.get("source_document_id") != document_id
            and ev.provenance.get("target_document_id") != document_id
        ]
        if len(self.relationships) != initial_count:
            self.record_event(
                CaseEventType.RELATIONSHIP_CHANGED,
                document_id=document_id,
                details={"action": "invalidated_stale_relationships", "purged": initial_count - len(self.relationships)},
            )
            # Risk assessment needs to be recalculated
            self.risk_assessment = None

    def record_event(
        self,
        event_type: CaseEventType | str,
        document_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        evt = create_audit_event(
            case_id=self.case_id,
            event_type=event_type,
            document_id=document_id,
            details=details,
        )
        self.audit_trail.append(evt)

    def to_response_dict(self) -> Dict[str, Any]:
        chain_blocks = [b for b in blockchain_ledger.get_chain(self.case_id) if b.block_index > 0]
        chain_valid, _ = blockchain_ledger.verify_chain(self.case_id)
        blockchain_summary = {
            "ledger_name": blockchain_ledger.ledger_name,
            "source_type": blockchain_ledger.source_type,
            "anchored_blocks": len(chain_blocks),
            "chain_valid": chain_valid,
            "status": "VERIFIED" if chain_valid and len(chain_blocks) > 0 else "ACTIVE",
        }

        return {
            "case_id": self.case_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "documents": [doc.to_summary_dict() for doc in self.get_active_documents()],
            "relationships": [rel.model_dump() for rel in self.relationships],
            "cross_document_evidence": [rel.model_dump() for rel in self.relationships],
            "risk_assessment": self.risk_assessment,
            "notes": self.notes,
            "audit_events": [evt.to_dict() for evt in self.audit_trail],
            "blockchain_audit": blockchain_summary,
        }
