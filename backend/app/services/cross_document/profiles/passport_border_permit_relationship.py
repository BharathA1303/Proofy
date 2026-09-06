"""
backend/app/services/cross_document/profiles/passport_border_permit_relationship.py

Canonical relationship profile between Passport and Border Permit credentials.
Primary relationship:
1. Border Permit linked passport reference binding (passport_number <-> document_number)
2. Holder name consistency
3. Date of birth consistency
"""
from __future__ import annotations

from app.schemas.cross_document import ComparisonMode, RelationshipType
from app.services.cross_document.relationship_profile import (
    RelationshipDefinition,
    RelationshipProfile,
)
from app.services.risk.risk_evidence import CorrelationGroup, EvidenceSeverity


def build_passport_border_permit_profile() -> RelationshipProfile:
    """
    Constructs the canonical relationship profile between Border Permit and Passport.
    Source: Border Permit
    Target: Passport (reference authority)
    """
    definitions = [
        RelationshipDefinition(
            source_field="passport_number",
            target_field="document_number",
            relationship_type=RelationshipType.IDENTIFIER_BINDING,
            comparison_mode=ComparisonMode.STRICT,
            severity_on_mismatch=EvidenceSeverity.HIGH,
            description="Linked passport number on Border Permit bound to Passport document number",
            confidence=0.99,
            correlation_group=CorrelationGroup.BORDER_PERMIT_PASSPORT_BINDING,
        ),
        RelationshipDefinition(
            source_field="name",
            target_field="name",
            relationship_type=RelationshipType.PERSON_NAME_CONSISTENCY,
            comparison_mode=ComparisonMode.NORMALIZED_TOKEN_SET,
            severity_on_mismatch=EvidenceSeverity.HIGH,
            description="Holder name consistency between Border Permit and Passport",
            confidence=0.95,
            correlation_group=CorrelationGroup.BORDER_PERMIT_PASSPORT_BINDING,
        ),
        RelationshipDefinition(
            source_field="date_of_birth",
            target_field="date_of_birth",
            relationship_type=RelationshipType.PERSON_ATTRIBUTE_CONSISTENCY,
            comparison_mode=ComparisonMode.NORMALIZED_DATE,
            severity_on_mismatch=EvidenceSeverity.HIGH,
            description="Date of birth consistency between Border Permit and Passport",
            confidence=0.98,
            correlation_group=CorrelationGroup.BORDER_PERMIT_DOB_CONSISTENCY,
        ),
    ]

    return RelationshipProfile(
        source_document_type="border_permit",
        target_document_type="passport",
        definitions=definitions,
    )
