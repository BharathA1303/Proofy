"""
backend/app/services/cross_document/profiles/passport_visa_relationship.py

Canonical relationship profile between Passport and Visa credentials.
"""
from __future__ import annotations

from app.schemas.cross_document import ComparisonMode, RelationshipType
from app.services.cross_document.relationship_profile import (
    RelationshipDefinition,
    RelationshipProfile,
)
from app.services.risk.risk_evidence import CorrelationGroup, EvidenceSeverity


def build_passport_visa_profile() -> RelationshipProfile:
    """
    Constructs the canonical relationship profile between Visa and Passport.
    Source: Visa (references passport)
    Target: Passport (reference authority)
    """
    definitions = [
        RelationshipDefinition(
            source_field="passport_number",
            target_field="document_number",
            relationship_type=RelationshipType.IDENTIFIER_BINDING,
            comparison_mode=ComparisonMode.STRICT,
            severity_on_mismatch=EvidenceSeverity.HIGH,
            description="Visa passport reference matches Passport document number",
            confidence=0.99,
            correlation_group=CorrelationGroup.DOCUMENT_NUMBER_BINDING,
        ),
        RelationshipDefinition(
            source_field="date_of_birth",
            target_field="date_of_birth",
            relationship_type=RelationshipType.PERSON_ATTRIBUTE_CONSISTENCY,
            comparison_mode=ComparisonMode.NORMALIZED_DATE,
            severity_on_mismatch=EvidenceSeverity.HIGH,
            description="Date of birth consistency between Visa and Passport",
            confidence=0.98,
        ),
        RelationshipDefinition(
            source_field="name",
            target_field="name",
            relationship_type=RelationshipType.PERSON_NAME_CONSISTENCY,
            comparison_mode=ComparisonMode.NORMALIZED_TOKEN_SET,
            severity_on_mismatch=EvidenceSeverity.HIGH,
            description="Bearer name consistency between Visa and Passport",
            confidence=0.95,
        ),
        RelationshipDefinition(
            source_field="nationality",
            target_field="nationality",
            relationship_type=RelationshipType.NATIONALITY_FIELD_CONSISTENCY,
            comparison_mode=ComparisonMode.NORMALIZED_CODE,
            severity_on_mismatch=EvidenceSeverity.HIGH,
            description="Nationality consistency between Visa and Passport",
            confidence=0.98,
        ),
    ]

    return RelationshipProfile(
        source_document_type="visa",
        target_document_type="passport",
        definitions=definitions,
    )
