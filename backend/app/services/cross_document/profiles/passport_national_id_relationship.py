"""
backend/app/services/cross_document/profiles/passport_national_id_relationship.py

Canonical relationship profile between Passport and National ID credentials.
Strictly evaluates bearer identity consistency (name, date/year of birth).
Does NOT compare National ID number with Passport number (distinct identifier domains).
"""
from __future__ import annotations

from app.schemas.cross_document import ComparisonMode, RelationshipType
from app.services.cross_document.relationship_profile import (
    RelationshipDefinition,
    RelationshipProfile,
)
from app.services.risk.risk_evidence import CorrelationGroup, EvidenceSeverity


def build_passport_national_id_profile() -> RelationshipProfile:
    """
    Constructs the canonical relationship profile between National ID and Passport.
    Source: National ID
    Target: Passport (reference authority)
    """
    definitions = [
        RelationshipDefinition(
            source_field="name",
            target_field="name",
            relationship_type=RelationshipType.PERSON_NAME_CONSISTENCY,
            comparison_mode=ComparisonMode.NORMALIZED_TOKEN_SET,
            severity_on_mismatch=EvidenceSeverity.HIGH,
            description="Bearer name consistency between National ID and Passport",
            confidence=0.95,
            correlation_group=CorrelationGroup.NID_PASSPORT_NAME_CONSISTENCY,
        ),
        RelationshipDefinition(
            source_field="date_of_birth",
            target_field="date_of_birth",
            relationship_type=RelationshipType.PERSON_ATTRIBUTE_CONSISTENCY,
            comparison_mode=ComparisonMode.NORMALIZED_DATE,
            severity_on_mismatch=EvidenceSeverity.HIGH,
            description="Date or Year of Birth consistency between National ID and Passport",
            confidence=0.98,
            correlation_group=CorrelationGroup.NID_PASSPORT_DOB_CONSISTENCY,
        ),
    ]

    return RelationshipProfile(
        source_document_type="national_id",
        target_document_type="passport",
        definitions=definitions,
    )
