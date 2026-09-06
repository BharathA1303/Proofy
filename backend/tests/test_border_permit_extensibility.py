"""
backend/tests/test_border_permit_extensibility.py

Extensibility proof for Phase 10:
Proves that a future 5th document type (Border Permit) can be added to the platform
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


class TestBorderPermitExtensibility:
    def test_border_permit_extension_without_modifying_engines(self):
        # 1. Register operational Border Permit DocumentProfile
        custom_doc_registry = DocumentProfileRegistry()
        bp_profile = DocumentProfile(
            document_type="border_permit",
            display_name="Border Permit",
            status=ProfileStatus.AVAILABLE,
            modules={
                "ocr": ModuleSupportStatus.SUPPORTED,
                "validation": ModuleSupportStatus.SUPPORTED,
                "forensics": ModuleSupportStatus.SUPPORTED,
                "biometrics": ModuleSupportStatus.SUPPORTED,
                "registry": ModuleSupportStatus.SUPPORTED,
                "risk": ModuleSupportStatus.SUPPORTED,
            },
            mrz_applicable=False,
            portrait_applicable=False,
            field_schema=["name", "docNumber", "permitType", "nationality", "portOfEntry", "expiry"],
            required_fields=["name", "docNumber"],
        )
        custom_doc_registry.register(bp_profile)
        assert custom_doc_registry.resolve_operational("border_permit") is not None

        # 2. Register Border Permit <-> Passport relationship profile
        custom_rel_registry = DocumentRelationshipRegistry()
        bp_passport_profile = RelationshipProfile(
            source_document_type="border_permit",
            target_document_type="passport",
            definitions=[
                RelationshipDefinition(
                    source_field="name",
                    target_field="name",
                    relationship_type=RelationshipType.PERSON_NAME_CONSISTENCY,
                    comparison_mode=ComparisonMode.NORMALIZED_TOKEN_SET,
                    description="Name match between Border Permit and Passport",
                ),
                RelationshipDefinition(
                    source_field="docNumber",
                    target_field="passport_number",
                    relationship_type=RelationshipType.IDENTIFIER_BINDING,
                    comparison_mode=ComparisonMode.STRICT,
                    description="Passport reference binding on Border Permit",
                ),
            ],
        )
        custom_rel_registry.register(bp_passport_profile)

        # 3. Instantiate generic engine with custom registry
        generic_cross_engine = CrossDocumentVerificationEngine(registry=custom_rel_registry)

        # 4. Evaluate fields
        bp_data = {"name": "ALEX DUPONT", "docNumber": "P554433", "permitType": "ENTRY"}
        passport_data = {"name": "ALEX DUPONT", "passport_number": "P554433", "document_number": "P554433", "date_of_birth": "1990-08-12"}

        doc1 = CaseDocument(
            document_id="DOC-001",
            document_type="passport",
            verification_id="vid-bp-p1",
            traveler_data=passport_data,
        )
        doc2 = CaseDocument(
            document_id="DOC-002",
            document_type="border_permit",
            verification_id="vid-bp-b1",
            traveler_data=bp_data,
        )

        evidence, m6_items = generic_cross_engine.evaluate_pair(doc1, doc2)

        assert len(evidence) == 2
        for ev in evidence:
            assert ev.status == RelationshipStatus.MATCHED

        # 5. Evaluate Case-level Risk in unmodified generic M6
        case = VerificationCase(case_id="CASE-BP-TEST")
        case.documents = {doc1.document_id: doc1, doc2.document_id: doc2}
        case.cross_document_evidence = m6_items
        case.relationships = evidence

        evaluator = CaseRiskEvaluator()
        assessment = evaluator.evaluate_case_risk(case)
        assert assessment["risk_score"] <= 25
        assert "DOC-001" in assessment["documents_considered"]
        assert "DOC-002" in assessment["documents_considered"]
