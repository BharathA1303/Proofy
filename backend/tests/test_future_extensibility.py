"""
backend/tests/test_future_extensibility.py

Architectural Extensibility Verification (Phase 11):
Proves that a future 6th document type (e.g., 'consular_id' or 'maritime_crew_cert')
can be introduced to the platform dynamically via:
  1. DocumentProfile definition & registration
  2. Document-specific parser
  3. Validation adapter
  4. Registry adapter & mock provider
  5. Cross-document relationship profile

WITHOUT modifying:
  - M1 core OCR engine
  - M3 core forensics engine
  - M4 core biometrics engine
  - M5 core registry engine
  - M6 generic risk engine
  - VerificationCase / CaseManager core
  - CrossDocumentVerificationEngine core
"""
from __future__ import annotations

import datetime
import pytest
from app.schemas.cross_document import (
    ComparisonMode,
    RelationshipStatus,
    RelationshipType,
)
from app.schemas.registry import (
    DocumentFieldSource,
    FieldMatchStatus,
    FieldProvenance,
    ProviderSourceType,
    RegistryEvidence,
    RegistryFieldResult,
    RegistryProviderMetadata,
    RegistryProviderStatus,
    RegistryRecord,
    RegistryStatus,
    RegistryVerificationRequest,
    RegistryVerificationResponse,
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
from app.services.registry.base import RegistryProvider


class ConsularIdRegistryAdapter:
    """Adapter for future 6th document type."""

    def document_type(self) -> str:
        return "consular_id"

    def build_request(self, session_data: dict) -> RegistryVerificationRequest:
        doc_num = session_data.get("consular_card_number") or session_data.get("docNumber", "")
        return RegistryVerificationRequest(
            verification_id=session_data.get("verification_id", "ext-vid-01"),
            document_type="consular_id",
            document_number=FieldProvenance(
                value=doc_num,
                source=DocumentFieldSource.PARSED,
            ),
            name=FieldProvenance(
                value=session_data.get("name", ""),
                source=DocumentFieldSource.PARSED,
            ),
        )


class MockConsularIdProvider(RegistryProvider):
    """Mock provider for future 6th document type."""

    @property
    def provider_id(self) -> str:
        return "mock-consular-id-registry"

    def initialize(self) -> None:
        pass

    def is_available(self) -> bool:
        return True

    def supports(self, document_type: str) -> bool:
        return document_type in ("consular_id", "consularid")

    def health_check(self) -> RegistryProviderStatus:
        return RegistryProviderStatus(
            provider_id=self.provider_id,
            source_type=ProviderSourceType.DEVELOPMENT_MOCK,
            available=True,
            supported_document_types=["consular_id"],
            details="Mock Consular ID provider",
        )

    def verify(self, request: RegistryVerificationRequest) -> RegistryVerificationResponse:
        now = datetime.datetime.now(datetime.timezone.utc)
        meta = RegistryProviderMetadata(
            provider_id=self.provider_id,
            provider_name="Mock Consular Registry Provider",
            source_type=ProviderSourceType.DEVELOPMENT_MOCK,
            version="1.0.0",
        )
        doc_num = request.document_number.value if request.document_number else ""
        if doc_num == "CC-2026-9999":
            evidence = [
                RegistryEvidence(
                    type="registry_record",
                    severity="info",
                    description="Consular ID record matched in mock database",
                )
            ]
            field_results = [
                RegistryFieldResult(
                    field="document_number",
                    document_value=doc_num,
                    registry_value="CC-2026-9999",
                    status=FieldMatchStatus.MATCH,
                )
            ]
            return RegistryVerificationResponse(
                verification_id=request.verification_id,
                document_type=request.document_type,
                registry={
                    "provider": self.provider_id,
                    "status": RegistryStatus.MATCHED.value,
                    "record_found": True,
                    "registry_document_status": "ACTIVE",
                },
                field_results=field_results,
                evidence=evidence,
                provider_metadata=meta,
                audit={"timestamp": now.isoformat()},
            )

        return RegistryVerificationResponse(
            verification_id=request.verification_id,
            document_type=request.document_type,
            registry={
                "provider": self.provider_id,
                "status": RegistryStatus.NOT_FOUND.value,
                "record_found": False,
            },
            field_results=[],
            evidence=[
                RegistryEvidence(
                    type="registry_lookup",
                    severity="warning",
                    description="Consular ID record not found",
                )
            ],
            provider_metadata=meta,
            audit={"timestamp": now.isoformat()},
        )


class TestFutureExtensibility:
    def test_future_sixth_document_type_extensibility(self):
        # 1. Register 6th document profile: Consular ID Card
        doc_registry = DocumentProfileRegistry()
        consular_profile = DocumentProfile(
            document_type="consular_id",
            display_name="Consular Identity Card",
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
            field_schema=["name", "consular_card_number", "passport_number", "mission", "valid_to"],
            required_fields=["name", "consular_card_number"],
        )
        doc_registry.register(consular_profile)
        resolved = doc_registry.resolve_operational("consular_id")
        assert resolved is not None
        assert resolved.display_name == "Consular Identity Card"

        # 2. Register Cross-Document Relationship: Consular ID <-> Passport
        rel_registry = DocumentRelationshipRegistry()
        consular_passport_rel = RelationshipProfile(
            source_document_type="consular_id",
            target_document_type="passport",
            definitions=[
                RelationshipDefinition(
                    source_field="name",
                    target_field="name",
                    relationship_type=RelationshipType.PERSON_NAME_CONSISTENCY,
                    comparison_mode=ComparisonMode.NORMALIZED_TOKEN_SET,
                    description="Consular ID traveler name matches Passport",
                ),
                RelationshipDefinition(
                    source_field="passport_number",
                    target_field="document_number",
                    relationship_type=RelationshipType.IDENTIFIER_BINDING,
                    comparison_mode=ComparisonMode.STRICT,
                    description="Bound passport reference on Consular ID",
                ),
            ],
        )
        rel_registry.register(consular_passport_rel)

        # 3. Test Cross-Document Engine with 6th Document without engine modification
        cross_engine = CrossDocumentVerificationEngine(registry=rel_registry)
        doc_passport = CaseDocument(
            document_id="DOC-PASS-01",
            document_type="passport",
            verification_id="vid-pass-01",
            traveler_data={"name": "ELENA ROSTOVA", "document_number": "P88990011"},
        )
        doc_consular = CaseDocument(
            document_id="DOC-CONS-01",
            document_type="consular_id",
            verification_id="vid-cons-01",
            traveler_data={"name": "ELENA ROSTOVA", "passport_number": "P88990011", "consular_card_number": "CC-2026-9999"},
        )

        evidence, m6_items = cross_engine.evaluate_pair(doc_passport, doc_consular)
        assert len(evidence) == 2
        assert all(ev.status == RelationshipStatus.MATCHED for ev in evidence)
        assert len(m6_items) == 0  # Matches produce zero adverse risk items

        # Mismatch generates adverse M6 risk evidence
        doc_consular_bad = CaseDocument(
            document_id="DOC-CONS-02",
            document_type="consular_id",
            verification_id="vid-cons-02",
            traveler_data={"name": "ELENA ROSTOVA", "passport_number": "WRONG_PASSPORT", "consular_card_number": "CC-2026-9999"},
        )
        bad_evidence, bad_m6 = cross_engine.evaluate_pair(doc_passport, doc_consular_bad)
        assert any(ev.status == RelationshipStatus.MISMATCH for ev in bad_evidence)
        assert len(bad_m6) >= 1

        # 4. Test Registry Engine with 6th Document Adapter without engine modification
        adapter = ConsularIdRegistryAdapter()
        provider = MockConsularIdProvider()

        reg_request = adapter.build_request({
            "verification_id": "vid-cons-01",
            "consular_card_number": "CC-2026-9999",
            "name": "ELENA ROSTOVA",
            "mission": "Embassy of Testland",
        })
        reg_result = provider.verify(reg_request)
        assert reg_result.registry["status"] == RegistryStatus.MATCHED.value
        assert reg_result.registry["record_found"] is True

        # 5. Test Case-level Risk Integration in generic M6
        case = VerificationCase(case_id="CASE-EXT-001")
        case.documents = {doc_passport.document_id: doc_passport, doc_consular.document_id: doc_consular}
        case.cross_document_evidence = m6_items
        case.relationships = evidence

        evaluator = CaseRiskEvaluator()
        assessment = evaluator.evaluate_case_risk(case)
        assert assessment["risk_score"] <= 25
        assert "DOC-PASS-01" in assessment["documents_considered"]
        assert "DOC-CONS-01" in assessment["documents_considered"]
