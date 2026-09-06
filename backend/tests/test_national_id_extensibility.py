"""
backend/tests/test_national_id_extensibility.py

Extensibility proof for Phase 9:
Proves that a future 4th document type (National ID) can be added to the platform
and case architecture without modifying:
  - CrossDocumentVerificationEngine core
  - Module 6 (Risk Engine)
  - Common OCR
  - Common forensics
  - Common biometrics
  - Common registry engine
"""
from __future__ import annotations

import pytest
from app.schemas.cross_document import (
    ComparisonMode,
    RelationshipStatus,
    RelationshipType,
)
from app.services.case.case_risk import CaseRiskEvaluator
from app.services.case.verification_case import CaseDocument, VerificationCase
from app.services.cross_document.cross_document_engine import CrossDocumentVerificationEngine
from app.services.cross_document.relationship_profile import (
    RelationshipDefinition,
    RelationshipProfile,
)
from app.services.cross_document.relationship_registry import DocumentRelationshipRegistry
from app.services.documents.profiles.document_profile import (
    DocumentProfile,
    ModuleSupportStatus,
    ProfileStatus,
)
from app.services.documents.profiles.document_profile_registry import DocumentProfileRegistry


class TestNationalIDExtensibility:
    def test_national_id_extension_without_modifying_engines(self):
        # 1. Register new National ID DocumentProfile
        custom_doc_registry = DocumentProfileRegistry()
        nid_profile = DocumentProfile(
            document_type="national_id",
            display_name="National ID",
            status=ProfileStatus.AVAILABLE,
            modules={
                "ocr": ModuleSupportStatus.SUPPORTED,
                "validation": ModuleSupportStatus.SUPPORTED,
                "forensics": ModuleSupportStatus.SUPPORTED,
                "biometrics": ModuleSupportStatus.SUPPORTED,
                "registry": ModuleSupportStatus.SUPPORTED,
                "risk": ModuleSupportStatus.SUPPORTED,
            },
            mrz_applicable=True,
            mrz_standard="TD1",
            portrait_applicable=True,
            field_schema=["name", "docNumber", "dob", "nationality", "gender", "expiry"],
            required_fields=["name", "docNumber", "dob"],
        )
        custom_doc_registry.register(nid_profile)
        assert custom_doc_registry.resolve("national_id") is not None

        # 2. Register National ID <-> Passport relationship profile
        custom_rel_registry = DocumentRelationshipRegistry()
        nid_passport_profile = RelationshipProfile(
            source_document_type="national_id",
            target_document_type="passport",
            definitions=[
                RelationshipDefinition(
                    source_field="name",
                    target_field="name",
                    relationship_type=RelationshipType.PERSON_NAME_CONSISTENCY,
                    comparison_mode=ComparisonMode.NORMALIZED_TOKEN_SET,
                    description="Name match between National ID and Passport",
                ),
                RelationshipDefinition(
                    source_field="dob",
                    target_field="date_of_birth",
                    relationship_type=RelationshipType.PERSON_ATTRIBUTE_CONSISTENCY,
                    comparison_mode=ComparisonMode.NORMALIZED_DATE,
                    description="DOB match between National ID and Passport",
                ),
            ],
        )
        custom_rel_registry.register(nid_passport_profile)

        # 3. Instantiate generic engine with custom registry
        generic_cross_engine = CrossDocumentVerificationEngine(registry=custom_rel_registry)

        # 4. Evaluate fields
        nid_data = {"name": "ALEX DUPONT", "dob": "1990-08-12", "docNumber": "NID98765"}
        passport_data = {"name": "ALEX DUPONT", "date_of_birth": "1990-08-12", "document_number": "P554433"}

        doc1 = CaseDocument(
            document_id="DOC-001",
            document_type="passport",
            verification_id="vid-nid-p1",
            traveler_data=passport_data,
        )
        doc2 = CaseDocument(
            document_id="DOC-002",
            document_type="national_id",
            verification_id="vid-nid-n1",
            traveler_data=nid_data,
        )

        evidence, m6_items = generic_cross_engine.evaluate_pair(doc1, doc2)

        assert len(evidence) == 2
        for ev in evidence:
            assert ev.status == RelationshipStatus.MATCHED

        # 5. Evaluate Case-level Risk in unmodified generic M6
        case = VerificationCase(case_id="CASE-NID-TEST")
        case.documents = {doc1.document_id: doc1, doc2.document_id: doc2}
        case.cross_document_evidence = m6_items
        case.relationships = evidence

        evaluator = CaseRiskEvaluator()
        assessment = evaluator.evaluate_case_risk(case)
        assert assessment["risk_score"] <= 25
        assert "DOC-001" in assessment["documents_considered"]
        assert "DOC-002" in assessment["documents_considered"]
