"""
backend/app/services/cross_document/cross_document_engine.py

Generic Cross-Document Verification Engine.
Evaluates relationship consistency across documents in a verification case,
producing field-level audit evidence and normalized M6 risk evidence.
"""
from __future__ import annotations

import itertools
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.cross_document import (
    CrossDocumentEvidenceItem,
    DocumentFieldReference,
    RelationshipStatus,
)
from app.services.case.case_audit import CaseEventType
from app.services.case.verification_case import CaseDocument, VerificationCase
from app.services.cross_document.relationship_comparator import RelationshipComparator
from app.services.cross_document.relationship_profile import RelationshipDefinition
from app.services.cross_document.relationship_registry import (
    DocumentRelationshipRegistry,
    relationship_registry,
)
from app.services.risk.risk_evidence import (
    EvidenceCategory,
    EvidenceSeverity,
    EvidenceStatus,
    RiskEvidenceItem,
)

logger = logging.getLogger(__name__)

# Field key aliases across camelCase and snake_case representations
FIELD_ALIASES: Dict[str, List[str]] = {
    "document_number": ["document_number", "docNumber", "doc_number", "passport_number", "identity_number", "identityNumber", "permit_number", "permitNumber"],
    "permit_number": ["permit_number", "permitNumber", "docNumber", "doc_number"],
    "passport_number": ["passport_number", "passportNumber"],
    "date_of_birth": ["date_of_birth", "dob", "year_of_birth", "yearOfBirth"],
    "year_of_birth": ["year_of_birth", "yearOfBirth", "dob", "date_of_birth"],
    "gender": ["gender", "sex"],
    "name": ["name", "fullName", "full_name"],
    "nationality": ["nationality"],
    "expiry_date": ["expiry_date", "expiry", "expirationDate", "valid_to", "validTo"],
    "issued_date": ["issued_date", "issuedDate", "issueDate", "valid_from", "validFrom"],
}


def _extract_field_value(traveler_data: Dict[str, Any], canonical_field: str) -> Optional[str]:
    """Retrieve value for canonical field using all known key aliases."""
    if canonical_field in traveler_data and traveler_data[canonical_field]:
        return str(traveler_data[canonical_field])

    aliases = FIELD_ALIASES.get(canonical_field, [canonical_field])
    for alias in aliases:
        val = traveler_data.get(alias)
        if val is not None and str(val).strip() != "":
            return str(val).strip()
    return None


class CrossDocumentVerificationEngine:
    """
    Evaluates cross-document relationships and produces normalized evidence.
    Does not make final autonomous immigration decisions.
    """

    def __init__(self, registry: Optional[DocumentRelationshipRegistry] = None) -> None:
        self._registry = registry or relationship_registry

    def evaluate_pair(
        self,
        doc_a: CaseDocument,
        doc_b: CaseDocument,
    ) -> Tuple[List[CrossDocumentEvidenceItem], List[RiskEvidenceItem]]:
        """
        Evaluate relationships between two documents in an order-independent manner.
        """
        resolution = self._registry.resolve_profile(doc_a.document_type, doc_b.document_type)
        if resolution is None:
            logger.debug(
                "CrossDocumentEngine: no relationship profile for %s <-> %s",
                doc_a.document_type, doc_b.document_type,
            )
            return [], []

        profile, is_reversed = resolution
        source_doc = doc_b if is_reversed else doc_a
        target_doc = doc_a if is_reversed else doc_b

        relationships: List[CrossDocumentEvidenceItem] = []
        risk_items: List[RiskEvidenceItem] = []

        counter = 0
        for definition in profile.definitions:
            counter += 1
            evidence_id = f"XDC-{source_doc.document_id}-{target_doc.document_id}-{counter:03d}"

            s_val = _extract_field_value(source_doc.traveler_data, definition.source_field)
            t_val = _extract_field_value(target_doc.traveler_data, definition.target_field)

            status, severity, explanation = RelationshipComparator.compare(
                source_val=s_val,
                target_val=t_val,
                mode=definition.comparison_mode,
                base_severity=definition.severity_on_mismatch,
            )

            rel_item = CrossDocumentEvidenceItem(
                evidence_id=evidence_id,
                relationship_type=definition.relationship_type,
                source_document=DocumentFieldReference(
                    document_id=source_doc.document_id,
                    document_type=source_doc.document_type,
                    field=definition.source_field,
                    value=s_val,
                ),
                target_document=DocumentFieldReference(
                    document_id=target_doc.document_id,
                    document_type=target_doc.document_type,
                    field=definition.target_field,
                    value=t_val,
                ),
                status=status,
                severity=severity.value,
                confidence=definition.confidence,
                explanation=explanation,
                provenance={
                    "source_document_id": source_doc.document_id,
                    "target_document_id": target_doc.document_id,
                    "source_field": definition.source_field,
                    "target_field": definition.target_field,
                    "comparison_mode": definition.comparison_mode.value,
                },
            )
            relationships.append(rel_item)

            # Map to canonical RiskEvidenceItem for Module 6
            if status in (RelationshipStatus.MISMATCH, RelationshipStatus.PARTIAL_MATCH):
                ev_status = (
                    EvidenceStatus.MISMATCH if status == RelationshipStatus.MISMATCH
                    else EvidenceStatus.WARNING
                )
                signal_name = f"cross_doc_{definition.relationship_type.value.lower()}_{status.value.lower()}"

                risk_items.append(RiskEvidenceItem(
                    module="CROSS_DOCUMENT",
                    signal=signal_name,
                    category=EvidenceCategory.DOCUMENT_CONSISTENCY,
                    status=ev_status,
                    severity=severity,
                    confidence=definition.confidence,
                    available=True,
                    explanation=explanation,
                    provenance={
                        "source_document_id": source_doc.document_id,
                        "target_document_id": target_doc.document_id,
                        "relationship_type": definition.relationship_type.value,
                        "evidence_id": evidence_id,
                    },
                    correlation_group=definition.correlation_group,
                ))

        return relationships, risk_items

    def evaluate_case(
        self,
        case: VerificationCase,
    ) -> Tuple[List[CrossDocumentEvidenceItem], List[RiskEvidenceItem]]:
        """
        Evaluate all active document pairs in a verification case.
        """
        active_docs = case.get_active_documents()
        all_relationships: List[CrossDocumentEvidenceItem] = []
        all_risk_items: List[RiskEvidenceItem] = []

        if len(active_docs) < 2:
            case.relationships = []
            case.cross_document_evidence = []
            return [], []

        # Iterate over all unordered unique pairs
        for doc_a, doc_b in itertools.combinations(active_docs, 2):
            rels, r_items = self.evaluate_pair(doc_a, doc_b)
            all_relationships.extend(rels)
            all_risk_items.extend(r_items)

        case.relationships = all_relationships
        case.cross_document_evidence = all_risk_items
        case.record_event(
            CaseEventType.CROSS_DOCUMENT_ANALYSIS_COMPLETED,
            details={"relationship_count": len(all_relationships), "adverse_evidence_count": len(all_risk_items)},
        )

        return all_relationships, all_risk_items


cross_document_engine = CrossDocumentVerificationEngine()
