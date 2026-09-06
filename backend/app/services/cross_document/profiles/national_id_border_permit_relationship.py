"""
backend/app/services/cross_document/profiles/national_id_border_permit_relationship.py

Canonical relationship profile between National ID and Border Permit credentials.
Evaluates bearer identity consistency (name, date of birth / year of birth).
Does NOT compare National ID number with Border Permit number.
"""
from __future__ import annotations

from app.schemas.cross_document import ComparisonMode, RelationshipType
from app.services.cross_document.relationship_profile import (
    RelationshipDefinition,
    RelationshipProfile,
)
from app.services.risk.risk_evidence import CorrelationGroup, EvidenceSeverity


def build_national_id_border_permit_profile() -> RelationshipProfile:
    """
    Constructs the canonical relationship profile between National ID and Border Permit.
    Source: National ID
    Target: Border Permit
    """
    definitions = [
        RelationshipDefinition(
            source_field="name",
            target_field="name",
            relationship_type=RelationshipType.PERSON_NAME_CONSISTENCY,
            comparison_mode=ComparisonMode.NORMALIZED_TOKEN_SET,
            severity_on_mismatch=EvidenceSeverity.HIGH,
            description="Bearer name consistency between National ID and Border Permit",
            confidence=0.95,
            correlation_group=CorrelationGroup.BORDER_PERMIT_PASSPORT_BINDING,
        ),
        RelationshipDefinition(
            source_field="date_of_birth",
            target_field="date_of_birth",
            relationship_type=RelationshipType.PERSON_ATTRIBUTE_CONSISTENCY,
            comparison_mode=ComparisonMode.NORMALIZED_DATE,
            severity_on_mismatch=EvidenceSeverity.HIGH,
            description="Date or Year of Birth consistency between National ID and Border Permit",
            confidence=0.98,
            correlation_group=CorrelationGroup.BORDER_PERMIT_DOB_CONSISTENCY,
        ),
    ]

    return RelationshipProfile(
        source_document_type="national_id",
        target_document_type="border_permit",
        definitions=definitions,
    )
