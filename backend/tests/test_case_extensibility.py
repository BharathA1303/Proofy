"""
tests/test_case_extensibility.py

Proves document profile extensibility for Phase 8:
A future document type (e.g., Driving License) can be added to the case
architecture without modifying:
  - CrossDocumentVerificationEngine
  - Module 6 (Risk Engine)
  - Common OCR
  - Common forensics
  - Common biometrics
  - Common registry engine

Only:
  - DocumentProfile registration
  - DocumentRelationshipProfile registration
are needed.
"""
from __future__ import annotations

from typing import Any, Dict
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
from app.services.documents.profiles.document_profile_registry import (
    DocumentProfileRegistry,
)


class TestDocumentExtensibility:
    """Proves zero-code modification of engines when extending to new document types."""

    def test_driving_license_extension_without_modifying_engines(self):
        # 1. Register new Driving License DocumentProfile
        custom_doc_registry = DocumentProfileRegistry()
        dl_profile = DocumentProfile(
            document_type="driving_license",
            display_name="Driving License",
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
            portrait_applicable=True,
            portrait_required=True,
            field_schema=["license_number", "name", "date_of_birth", "address"],
            required_fields=["license_number", "name", "date_of_birth"],
        )
        custom_doc_registry.register(dl_profile)
        assert custom_doc_registry.is_supported("driving_license")
        assert custom_doc_registry.resolve_operational("driving_license") is not None

        # 2. Register Driving License <-> Passport Relationship Profile
        custom_rel_registry = DocumentRelationshipRegistry()
        dl_passport_profile = RelationshipProfile(
            source_document_type="driving_license",
            target_document_type="passport",
            definitions=[
                RelationshipDefinition(
                    source_field="name",
                    target_field="name",
                    relationship_type=RelationshipType.PERSON_NAME_CONSISTENCY,
                    comparison_mode=ComparisonMode.NORMALIZED_TOKEN_SET,
                    severity_on_mismatch="LOW",
                ),
                RelationshipDefinition(
                    source_field="date_of_birth",
                    target_field="date_of_birth",
                    relationship_type=RelationshipType.PERSON_ATTRIBUTE_CONSISTENCY,
                    comparison_mode=ComparisonMode.NORMALIZED_DATE,
                    severity_on_mismatch="HIGH",
                ),
                RelationshipDefinition(
                    source_field="license_number",
                    target_field="document_number",
                    relationship_type=RelationshipType.IDENTIFIER_BINDING,
                    comparison_mode=ComparisonMode.STRICT,
                    severity_on_mismatch="HIGH",
                ),
            ],
        )
        custom_rel_registry.register(dl_passport_profile)

        # 3. Instantiate generic CrossDocumentVerificationEngine with this registry
        # Notice: CrossDocumentVerificationEngine has ZERO DL-specific code!
        engine = CrossDocumentVerificationEngine(registry=custom_rel_registry)

        # 4. Create case with a Passport and a Driving License
        case = VerificationCase(case_id="CASE-EXT-001")
        doc_passport = CaseDocument(
            document_id="DOC-001",
            document_type="passport",
            verification_id="vid-p",
            filename="passport.jpg",
            traveler_data={
                "document_number": "DL999888",
                "name": "JANE SMITH",
                "date_of_birth": "1988-03-24",
            },
        )
        doc_dl = CaseDocument(
            document_id="DOC-002",
            document_type="driving_license",
            verification_id="vid-dl",
            filename="license.jpg",
            traveler_data={
                "license_number": "DL999888",
                "name": "JANE SMITH",
                "date_of_birth": "1988-03-24",
            },
        )
        case.add_document(doc_passport)
        case.add_document(doc_dl)

        # 5. Execute cross-document engine
        engine.evaluate_case(case)

        # Verify all 3 custom relationships evaluated correctly to MATCHED
        assert len(case.relationships) == 3
        for rel in case.relationships:
            assert rel.status == RelationshipStatus.MATCHED
            assert rel.severity == "NONE"

        # 6. Pass into unchanged CaseRiskEvaluator / M6
        risk_evaluator = CaseRiskEvaluator()
        assessment = risk_evaluator.evaluate_case_risk(case)

        assert assessment["risk_score"] == 0
        assert assessment["risk_level"] in ("LOW", "CLEAR")
        assert len(assessment["documents_considered"]) == 2
        assert "DOC-001" in assessment["documents_considered"]
        assert "DOC-002" in assessment["documents_considered"]
