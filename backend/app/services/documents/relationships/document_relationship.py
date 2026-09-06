"""
backend/app/services/documents/relationships/document_relationship.py

Generic Cross-Document Relationship Architecture.

Provides consistent tracking and comparison of cross-referenced credentials
(e.g., Visa referencing a Passport, DL referencing a National ID, Border Permit referencing Passport).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class RelationshipType(str, Enum):
    """Canonical relationship types across documents."""
    PASSPORT_REFERENCE = "passport_reference"
    IDENTITY_REFERENCE = "identity_reference"
    PERMIT_AUTHORIZATION = "permit_authorization"


class RelationshipStatus(str, Enum):
    """Evaluation status of a cross-document relationship."""
    MATCHED = "MATCHED"
    MISMATCH = "MISMATCH"
    MISMATCHED = "MISMATCH"
    NOT_EVALUATED = "NOT_EVALUATED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class DocumentRelationship:
    """
    Representation of a directional cross-document field reference.

    Example:
      source_document: "visa"
      source_field:    "passport_number" (e.g. "T9876543")
      target_document: "passport"
      target_field:    "document_number" (e.g. "T9876543")
      status:          "MATCHED"
    """
    relationship_type: str
    source_document: str
    source_field: str
    target_document: str
    target_field: str
    status: RelationshipStatus
    source_value: Optional[str] = None
    target_value: Optional[str] = None
    explanation: str = ""

    @property
    def details(self) -> str:
        return self.explanation

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for session storage and audit trails."""
        return {
            "relationship_type": self.relationship_type,
            "source_document": self.source_document,
            "source_field": self.source_field,
            "target_document": self.target_document,
            "target_field": self.target_field,
            "status": self.status.value,
            "source_value": self.source_value,
            "target_value": self.target_value,
            "explanation": self.explanation,
        }


def evaluate_relationship(
    source_doc_type: str,
    source_field: str,
    source_val: Optional[str],
    target_doc_type: str,
    target_field: str,
    target_val: Optional[str],
    relationship_type: str = RelationshipType.PASSPORT_REFERENCE.value,
) -> DocumentRelationship:
    """
    Evaluate a generic directional reference between two documents.

    If target document or value is not available, returns NOT_EVALUATED
    so verification can continue independently.
    """
    s_clean = (source_val or "").strip()
    t_clean = (target_val or "").strip()

    if not s_clean and not t_clean:
        return DocumentRelationship(
            relationship_type=relationship_type,
            source_document=source_doc_type,
            source_field=source_field,
            target_document=target_doc_type,
            target_field=target_field,
            status=RelationshipStatus.UNAVAILABLE,
            explanation=f"Neither {source_doc_type}.{source_field} nor {target_doc_type}.{target_field} provided.",
        )

    if not s_clean:
        return DocumentRelationship(
            relationship_type=relationship_type,
            source_document=source_doc_type,
            source_field=source_field,
            target_document=target_doc_type,
            target_field=target_field,
            status=RelationshipStatus.UNAVAILABLE,
            source_value=None,
            target_value=t_clean,
            explanation=f"{source_doc_type}.{source_field} not extracted from credential.",
        )

    if not t_clean:
        return DocumentRelationship(
            relationship_type=relationship_type,
            source_document=source_doc_type,
            source_field=source_field,
            target_document=target_doc_type,
            target_field=target_field,
            status=RelationshipStatus.UNAVAILABLE,
            source_value=s_clean,
            target_value=None,
            explanation=f"Target document ({target_doc_type}) not available in session.",
        )

    # Normalize alphanumeric identifiers for comparison
    s_norm = re.sub(r"[^A-Z0-9]", "", s_clean.upper())
    t_norm = re.sub(r"[^A-Z0-9]", "", t_clean.upper())

    if s_norm == t_norm:
        status = RelationshipStatus.MATCHED
        explanation = (
            f"Cross-document consistency confirmed: {source_doc_type}.{source_field} "
            f"matches {target_doc_type}.{target_field} ('{s_clean}')."
        )
    else:
        status = RelationshipStatus.MISMATCH
        explanation = (
            f"Cross-document mismatch: {source_doc_type}.{source_field} ('{s_clean}') "
            f"does not match {target_doc_type}.{target_field} ('{t_clean}')."
        )

    return DocumentRelationship(
        relationship_type=relationship_type,
        source_document=source_doc_type,
        source_field=source_field,
        target_document=target_doc_type,
        target_field=target_field,
        status=status,
        source_value=s_clean,
        target_value=t_clean,
        explanation=explanation,
    )


def evaluate_visa_passport_relationship(
    visa_passport_number: Optional[str] = None,
    passport_doc_number: Optional[str] = None,
    actual_passport_number: Optional[str] = None,
) -> DocumentRelationship:
    """
    Convenience evaluator for Visa.passport_number ↔ Passport.document_number.
    """
    target_val = passport_doc_number if passport_doc_number is not None else actual_passport_number
    return evaluate_relationship(
        source_doc_type="visa",
        source_field="passport_number",
        source_val=visa_passport_number,
        target_doc_type="passport",
        target_field="document_number",
        target_val=target_val,
        relationship_type=RelationshipType.PASSPORT_REFERENCE.value,
    )
