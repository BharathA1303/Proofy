"""
backend/tests/test_cross_document_engine.py

Unit tests for RelationshipComparator, DocumentRelationshipRegistry,
and CrossDocumentVerificationEngine.
"""
import pytest
from app.schemas.cross_document import ComparisonMode, RelationshipStatus, RelationshipType
from app.services.case.verification_case import CaseDocument, VerificationCase
from app.services.cross_document.cross_document_engine import CrossDocumentVerificationEngine
from app.services.cross_document.relationship_comparator import RelationshipComparator
from app.services.cross_document.relationship_registry import DocumentRelationshipRegistry
from app.services.risk.risk_evidence import CorrelationGroup, EvidenceSeverity


class TestRelationshipComparator:
    def test_strict_identifier_matching(self):
        # Exact match
        status, sev, exp = RelationshipComparator.compare(
            "T9876543", "T9876543", ComparisonMode.STRICT, EvidenceSeverity.HIGH
        )
        assert status == RelationshipStatus.MATCHED
        assert sev == EvidenceSeverity.NONE

        # Normalized punctuation/whitespace still matches
        status, sev, exp = RelationshipComparator.compare(
            "T 9876-543", "T9876543", ComparisonMode.STRICT, EvidenceSeverity.HIGH
        )
        assert status == RelationshipStatus.MATCHED

        # Mismatch
        status, sev, exp = RelationshipComparator.compare(
            "T9876548", "T9876543", ComparisonMode.STRICT, EvidenceSeverity.HIGH
        )
        assert status == RelationshipStatus.MISMATCH
        assert sev == EvidenceSeverity.HIGH

    def test_normalized_date_comparison(self):
        status, sev, _ = RelationshipComparator.compare(
            "1990-06-15", "15/06/1990", ComparisonMode.NORMALIZED_DATE, EvidenceSeverity.HIGH
        )
        assert status == RelationshipStatus.MATCHED
        assert sev == EvidenceSeverity.NONE

        status, sev, _ = RelationshipComparator.compare(
            "1990-06-15", "1992-01-01", ComparisonMode.NORMALIZED_DATE, EvidenceSeverity.HIGH
        )
        assert status == RelationshipStatus.MISMATCH
        assert sev == EvidenceSeverity.HIGH

    def test_name_token_comparison_conservative_matching(self):
        # Identical tokens
        status, sev, _ = RelationshipComparator.compare(
            "JOHN DOE", "DOE JOHN", ComparisonMode.NORMALIZED_TOKEN_SET, EvidenceSeverity.HIGH
        )
        assert status == RelationshipStatus.MATCHED
        assert sev == EvidenceSeverity.NONE

        # Token subset overlap (e.g. middle initial/name difference) -> PARTIAL_MATCH (LOW severity)
        status, sev, _ = RelationshipComparator.compare(
            "JOHN DOE", "JOHN A DOE", ComparisonMode.NORMALIZED_TOKEN_SET, EvidenceSeverity.HIGH
        )
        assert status == RelationshipStatus.PARTIAL_MATCH
        assert sev == EvidenceSeverity.LOW  # Never falsely flag fraud for formatting variation

        # Disjoint name mismatch
        status, sev, _ = RelationshipComparator.compare(
            "SARAH CONNOR", "JOHN DOE", ComparisonMode.NORMALIZED_TOKEN_SET, EvidenceSeverity.HIGH
        )
        assert status == RelationshipStatus.MISMATCH
        assert sev == EvidenceSeverity.HIGH

    def test_missing_fields_handling(self):
        status, sev, _ = RelationshipComparator.compare(
            None, "T9876543", ComparisonMode.STRICT
        )
        assert status == RelationshipStatus.MISSING_SOURCE_FIELD

        status, sev, _ = RelationshipComparator.compare(
            "T9876543", None, ComparisonMode.STRICT
        )
        assert status == RelationshipStatus.MISSING_TARGET_FIELD

        status, sev, _ = RelationshipComparator.compare(
            None, None, ComparisonMode.STRICT
        )
        assert status == RelationshipStatus.UNAVAILABLE


class TestRelationshipRegistryAndEngine:
    def test_order_independent_profile_resolution(self):
        registry = DocumentRelationshipRegistry()
        res1 = registry.resolve_profile("visa", "passport")
        assert res1 is not None
        prof1, is_rev1 = res1
        assert prof1.source_document_type == "visa"
        assert prof1.target_document_type == "passport"
        assert is_rev1 is False

        # Reversed query (passport first)
        res2 = registry.resolve_profile("passport", "visa")
        assert res2 is not None
        prof2, is_rev2 = res2
        assert prof2.source_document_type == "visa"
        assert prof2.target_document_type == "passport"
        assert is_rev2 is True

    def test_engine_evaluates_pair_and_produces_evidence_with_correlation_group(self):
        engine = CrossDocumentVerificationEngine()

        doc_visa = CaseDocument(
            document_id="DOC-V-1",
            document_type="visa",
            verification_id="vid-v",
            traveler_data={
                "docNumber": "V12345678",
                "passportNumber": "T9876543",
                "name": "SARAH CONNOR",
                "dob": "1985-05-12",
                "nationality": "USA",
            },
        )

        doc_passport = CaseDocument(
            document_id="DOC-P-1",
            document_type="passport",
            verification_id="vid-p",
            traveler_data={
                "docNumber": "T9876543",
                "name": "SARAH CONNOR",
                "dob": "1985-05-12",
                "nationality": "USA",
            },
        )

        rels, risk_items = engine.evaluate_pair(doc_visa, doc_passport)
        assert len(rels) == 4
        # All 4 fields match perfectly
        assert all(r.status == RelationshipStatus.MATCHED for r in rels)
        # No adverse risk items
        assert len(risk_items) == 0

        # Now test with passport mismatch
        doc_visa.traveler_data["passportNumber"] = "MISMATCH999"
        rels_bad, risk_items_bad = engine.evaluate_pair(doc_visa, doc_passport)
        mismatch_rel = next(r for r in rels_bad if r.relationship_type == RelationshipType.IDENTIFIER_BINDING)
        assert mismatch_rel.status == RelationshipStatus.MISMATCH

        # Check risk item has DOCUMENT_NUMBER_BINDING correlation group for double-counting protection
        assert len(risk_items_bad) == 1
        assert risk_items_bad[0].correlation_group == CorrelationGroup.DOCUMENT_NUMBER_BINDING
        assert risk_items_bad[0].severity == EvidenceSeverity.HIGH
