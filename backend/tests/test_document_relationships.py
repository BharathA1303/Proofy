"""
tests/test_document_relationships.py

Tests for Cross-Document Relationship Architecture (Visa passport reference <-> Passport document).
"""
import pytest
from app.schemas.ocr import TravelerFields
from app.services.documents.relationships.document_relationship import (
    DocumentRelationship,
    RelationshipStatus,
    RelationshipType,
    evaluate_relationship,
    evaluate_visa_passport_relationship,
)
from app.services.documents.visa.visa_validator import validate_visa_document


class TestDocumentRelationships:
    def test_matching_passport_reference(self):
        rel = evaluate_visa_passport_relationship(
            visa_passport_number="T9876543",
            actual_passport_number="T9876543",
        )
        assert rel.status == RelationshipStatus.MATCHED
        assert rel.source_value == "T9876543"
        assert rel.target_value == "T9876543"
        assert "matches" in rel.details.lower()

    def test_mismatched_passport_reference(self):
        rel = evaluate_visa_passport_relationship(
            visa_passport_number="T9876548",
            actual_passport_number="T9876543",
        )
        assert rel.status == RelationshipStatus.MISMATCHED
        assert rel.source_value == "T9876548"
        assert rel.target_value == "T9876543"
        assert "mismatch" in rel.details.lower()

    def test_missing_visa_passport_number(self):
        rel = evaluate_visa_passport_relationship(
            visa_passport_number=None,
            actual_passport_number="T9876543",
        )
        assert rel.status == RelationshipStatus.UNAVAILABLE
        assert "not extracted" in rel.details.lower()

    def test_missing_actual_passport(self):
        rel = evaluate_visa_passport_relationship(
            visa_passport_number="T9876543",
            actual_passport_number=None,
        )
        assert rel.status == RelationshipStatus.UNAVAILABLE
        assert "not available" in rel.details.lower()

    def test_visa_validation_with_matching_passport(self):
        traveler = TravelerFields(
            name="JACK SPARROW",
            docNumber="V12345678",
            expiry="2030-01-01",
            passportNumber="P1234567",
        )
        result = validate_visa_document(traveler, related_passport_number="P1234567")
        assert result["status"] == "passed"
        assert "cross_document_passport" in result["checks"]
        assert result["checks"]["cross_document_passport"]["status"] == "passed"
        assert result["checks"]["cross_document_passport"]["valid"] is True

    def test_visa_validation_with_mismatched_passport_fails(self):
        traveler = TravelerFields(
            name="JACK SPARROW",
            docNumber="V12345678",
            expiry="2030-01-01",
            passportNumber="P1234567",
        )
        result = validate_visa_document(traveler, related_passport_number="P9999999")
        assert result["status"] == "failed"
        assert "cross_document_passport" in result["checks"]
        assert result["checks"]["cross_document_passport"]["status"] == "failed"
        assert any(i["check"] == "cross_document_passport" and i["severity"] == "critical" for i in result["issues"])
