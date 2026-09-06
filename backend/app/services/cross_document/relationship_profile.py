"""
backend/app/services/cross_document/relationship_profile.py

Defines configurable relationship specifications between document types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.schemas.cross_document import ComparisonMode, RelationshipType
from app.services.risk.risk_evidence import CorrelationGroup, EvidenceSeverity


@dataclass(frozen=True)
class RelationshipDefinition:
    """Configurable definition of a relationship between two fields."""
    source_field: str
    target_field: str
    relationship_type: RelationshipType
    comparison_mode: ComparisonMode
    severity_on_mismatch: EvidenceSeverity = EvidenceSeverity.HIGH
    description: str = ""
    confidence: float = 0.99
    correlation_group: Optional[CorrelationGroup] = None


@dataclass
class RelationshipProfile:
    """Bundle of relationship definitions for a pair of document types."""
    source_document_type: str
    target_document_type: str
    definitions: List[RelationshipDefinition] = field(default_factory=list)

    @property
    def pair_key(self) -> tuple[str, str]:
        return (self.source_document_type.lower(), self.target_document_type.lower())

    def get_definition(self, source_field: str, target_field: str) -> Optional[RelationshipDefinition]:
        for d in self.definitions:
            if d.source_field == source_field and d.target_field == target_field:
                return d
        return None
