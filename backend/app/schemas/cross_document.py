"""
backend/app/schemas/cross_document.py

Pydantic v2 schemas for Cross-Document Intelligence and Relationship Evidence.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class RelationshipType(str, Enum):
    """Canonical relationship types across documents."""
    IDENTIFIER_BINDING = "IDENTIFIER_BINDING"
    PERSON_ATTRIBUTE_CONSISTENCY = "PERSON_ATTRIBUTE_CONSISTENCY"
    PERSON_NAME_CONSISTENCY = "PERSON_NAME_CONSISTENCY"
    NATIONALITY_FIELD_CONSISTENCY = "NATIONALITY_FIELD_CONSISTENCY"
    DATE_CHRONOLOGY = "DATE_CHRONOLOGY"


class RelationshipStatus(str, Enum):
    """Discrete outcome of evaluating a cross-document relationship."""
    MATCHED = "MATCHED"
    MISMATCH = "MISMATCH"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    CONSISTENT_YEAR = "CONSISTENT_YEAR"
    MISSING_SOURCE_FIELD = "MISSING_SOURCE_FIELD"
    MISSING_TARGET_FIELD = "MISSING_TARGET_FIELD"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNAVAILABLE = "UNAVAILABLE"
    INCONCLUSIVE = "INCONCLUSIVE"


class ComparisonMode(str, Enum):
    """Mode of comparison for cross-document field pairs."""
    STRICT = "STRICT"
    NORMALIZED_DATE = "NORMALIZED_DATE"
    NORMALIZED_TOKEN_SET = "NORMALIZED_TOKEN_SET"
    NORMALIZED_CODE = "NORMALIZED_CODE"


class DocumentFieldReference(BaseModel):
    """Reference to a field within a specific document in a case."""
    document_id: str
    document_type: str
    field: str
    value: Optional[str] = None
    masked_value: Optional[str] = None


class CrossDocumentEvidenceItem(BaseModel):
    """Normalized evidence produced by evaluating a cross-document relationship."""
    evidence_id: str
    relationship_type: RelationshipType
    source_document: DocumentFieldReference
    target_document: DocumentFieldReference
    status: RelationshipStatus
    severity: str = "NONE"  # NONE, LOW, MEDIUM, HIGH, CRITICAL
    confidence: float = 1.0
    explanation: str = ""
    provenance: Dict[str, Any] = Field(default_factory=dict)
