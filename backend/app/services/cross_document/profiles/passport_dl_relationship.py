"""
backend/app/services/cross_document/profiles/passport_dl_relationship.py

Canonical relationship profile between Passport and Driving License credentials.
Strictly evaluates holder identity consistency (name, date of birth).
Does NOT compare license number with passport number (distinct identifier domains).
"""
from __future__ import annotations

from app.schemas.cross_document import ComparisonMode, RelationshipType
from app.services.cross_document.relationship_profile import (
    RelationshipDefinition,
    RelationshipProfile,
)
from app.services.risk.risk_evidence import CorrelationGroup, EvidenceSeverity


def build_passport_dl_profile() -> RelationshipProfile:
    """
    Constructs the canonical relationship profile between Driving License and Passport.
    Source: Driving License
    Target: Passport (reference authority)
    """
    definitions = [
        RelationshipDefinition(
            source_field="name",
            target_field="name",
            relationship_type=RelationshipType.PERSON_NAME_CONSISTENCY,
            comparison_mode=ComparisonMode.NORMALIZED_TOKEN_SET,
            severity_on_mismatch=EvidenceSeverity.HIGH,
            description="Bearer name consistency between Driving License and Passport",
            confidence=0.95,
        ),
        RelationshipDefinition(
            source_field="date_of_birth",
            target_field="date_of_birth",
            relationship_type=RelationshipType.PERSON_ATTRIBUTE_CONSISTENCY,
            comparison_mode=ComparisonMode.NORMALIZED_DATE,
            severity_on_mismatch=EvidenceSeverity.HIGH,
            description="Date of birth consistency between Driving License and Passport",
            confidence=0.98,
            correlation_group=CorrelationGroup.DOB_CONSISTENCY,
        ),
    ]

    return RelationshipProfile(
        source_document_type="driving_license",
        target_document_type="passport",
        definitions=definitions,
    )
