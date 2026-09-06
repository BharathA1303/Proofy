"""
backend/app/services/documents/relationships/__init__.py

Cross-document relationships package.
"""
from app.services.documents.relationships.document_relationship import (
    DocumentRelationship,
    RelationshipStatus,
    RelationshipType,
    evaluate_relationship,
    evaluate_visa_passport_relationship,
)

__all__ = [
    "DocumentRelationship",
    "RelationshipStatus",
    "RelationshipType",
    "evaluate_relationship",
    "evaluate_visa_passport_relationship",
]
