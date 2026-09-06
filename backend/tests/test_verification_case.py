"""
backend/tests/test_verification_case.py

Unit tests for VerificationCase domain models, case store, and audit events.
"""
import pytest
from app.schemas.case import CaseStatus, DocumentStatus
from app.schemas.cross_document import (
    CrossDocumentEvidenceItem,
    DocumentFieldReference,
    RelationshipStatus,
    RelationshipType,
)
from app.services.case.case_audit import CaseEventType
from app.services.case.case_store import VerificationCaseStore
from app.services.case.verification_case import CaseDocument, VerificationCase
from app.services.risk.risk_evidence import EvidenceCategory, EvidenceSeverity, EvidenceStatus, RiskEvidenceItem


class TestVerificationCaseModels:
    def test_case_initialization_and_document_addition(self):
        case = VerificationCase(case_id="CASE-TEST-001")
        assert case.case_id == "CASE-TEST-001"
        assert case.status == CaseStatus.ACTIVE
        assert len(case.documents) == 0

        doc1 = CaseDocument(
            document_id="DOC-001",
            document_type="passport",
            verification_id="vid-1",
            traveler_data={"docNumber": "P12345678", "name": "ALICE SMITH"},
        )
        case.add_document(doc1)

        assert len(case.documents) == 1
        assert case.has_document_type("passport")
        assert not case.has_document_type("visa")
        assert case.active_document_id == "DOC-001"
        assert any(e.event_type == CaseEventType.DOCUMENT_ADDED.value for e in case.audit_trail)

    def test_document_superseding_invalidates_dependent_relationships(self):
        case = VerificationCase(case_id="CASE-TEST-002")
        doc1 = CaseDocument(
            document_id="DOC-001",
            document_type="passport",
            verification_id="vid-1",
            document_revision=1,
        )
        case.add_document(doc1)

        # Attach a mock relationship
        rel = CrossDocumentEvidenceItem(
            evidence_id="XDC-001",
            relationship_type=RelationshipType.IDENTIFIER_BINDING,
            source_document=DocumentFieldReference(document_id="DOC-002", document_type="visa", field="passport_number"),
            target_document=DocumentFieldReference(document_id="DOC-001", document_type="passport", field="document_number"),
            status=RelationshipStatus.MATCHED,
            severity="NONE",
            explanation="Matched",
        )
        case.relationships.append(rel)

        # Attach a mock risk evidence item
        risk_ev = RiskEvidenceItem(
            module="CROSS_DOCUMENT",
            signal="cross_doc_binding",
            category=EvidenceCategory.DOCUMENT_CONSISTENCY,
            status=EvidenceStatus.MATCH,
            severity=EvidenceSeverity.NONE,
            confidence=0.99,
            available=True,
            explanation="Matched",
            provenance={"source_document_id": "DOC-002", "target_document_id": "DOC-001"},
        )
        case.cross_document_evidence.append(risk_ev)
        assert len(case.relationships) == 1
        assert len(case.cross_document_evidence) == 1

        # Now supersede DOC-001 with replacement
        old_doc = case.supersede_document_type("passport")
        assert old_doc is not None
        assert old_doc.status == DocumentStatus.SUPERSEDED

        # Relationships involving DOC-001 must be purged / invalidated
        assert len(case.relationships) == 0
        assert len(case.cross_document_evidence) == 0
        assert any(e.event_type == CaseEventType.DOCUMENT_REPLACED.value for e in case.audit_trail)

    def test_document_removal_updates_case_and_active_document(self):
        case = VerificationCase(case_id="CASE-TEST-003")
        doc1 = CaseDocument(document_id="DOC-001", document_type="passport", verification_id="vid-1")
        doc2 = CaseDocument(document_id="DOC-002", document_type="visa", verification_id="vid-2")
        case.add_document(doc1)
        case.add_document(doc2)

        assert case.active_document_id == "DOC-002"
        assert len(case.get_active_documents()) == 2

        removed = case.remove_document("DOC-002")
        assert removed is not None
        assert removed.status == DocumentStatus.REMOVED
        assert len(case.get_active_documents()) == 1
        assert case.active_document_id == "DOC-001"
        assert any(e.event_type == CaseEventType.DOCUMENT_REMOVED.value for e in case.audit_trail)


class TestVerificationCaseStore:
    def test_store_crud_and_eviction(self):
        store = VerificationCaseStore(ttl_seconds=300, max_entries=2)
        c1 = VerificationCase(case_id="C-1")
        c2 = VerificationCase(case_id="C-2")
        c3 = VerificationCase(case_id="C-3")

        store.set("C-1", c1)
        store.set("C-2", c2)
        assert store.has("C-1")
        assert store.get("C-1") is c1

        # Adding 3rd should evict oldest (C-2 was least recently accessed)
        store.set("C-3", c3)
        assert store.has("C-1")
        assert store.has("C-3")

        assert store.delete("C-1") is True
        assert store.delete("C-NONEXISTENT") is False
        assert not store.has("C-1")
