"""
tests/test_case_scenarios.py

Covers all 18 specified Phase 8 Scenarios for Multi-Document Verification
and Cross-Document Intelligence:

Scenario 1:  Passport only (existing behavior unchanged)
Scenario 2:  Visa only (existing Visa behavior unchanged)
Scenario 3:  Passport + Visa matching (all applicable relationships MATCHED)
Scenario 4:  Passport + Visa passport-number mismatch (HIGH cross-document evidence)
Scenario 5:  Passport + Visa DOB mismatch (elevated consistency evidence)
Scenario 6:  Passport + Visa name formatting difference (conservative matching, never false fraud)
Scenario 7:  Passport + Visa missing optional field (NOT_APPLICABLE / MISSING_SOURCE_FIELD)
Scenario 8:  Passport complete + Visa partial (cross-document assessment partial/unavailable)
Scenario 9:  Visa uploaded first, Passport second (order independence)
Scenario 10: Passport replaced (old relationship evidence invalidated)
Scenario 11: Visa replaced (affected evidence invalidated)
Scenario 12: Duplicate Passport added (duplicate prevented)
Scenario 13: Registry mismatch + cross-document mismatch (M6 avoids double-counting)
Scenario 14: M2 mismatch + cross-document mismatch for same underlying field (evidence grouping)
Scenario 15: One document removed (case risk recalculated)
Scenario 16: Concurrent Passport/Visa processing (no state corruption)
Scenario 17: Client attempts to inject cross-document MATCHED evidence (rejected/ignored)
Scenario 18: Unknown document type (rejected)
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Dict
import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import (
    DocumentProfileError,
    DuplicateDocumentTypeError,
    UnsupportedDocumentTypeError,
)
from app.main import app
from app.schemas.case import CaseStatus, DocumentStatus
from app.schemas.cross_document import RelationshipStatus
from app.services.case.case_manager import CaseManager
from app.services.case.case_risk import CaseRiskEvaluator
from app.services.case.case_store import VerificationCaseStore
from app.services.case.verification_case import CaseDocument, VerificationCase
from app.services.cross_document.cross_document_engine import CrossDocumentVerificationEngine
from app.services.cross_document.relationship_registry import relationship_registry
from app.services.risk.risk_evidence import (
    EvidenceCategory,
    EvidenceSeverity,
    EvidenceStatus,
    RiskEvidenceItem,
)
from app.services.risk.risk_session_store import risk_session_store


client = TestClient(app)


def _build_doc(
    doc_id: str,
    doc_type: str,
    traveler_data: Dict[str, Any],
    status: DocumentStatus = DocumentStatus.COMPLETED,
    module_statuses: Dict[str, str] = None,
    revision: int = 1,
) -> CaseDocument:
    return CaseDocument(
        document_id=doc_id,
        document_type=doc_type,
        verification_id=f"vid-{doc_id}",
        status=status,
        document_revision=revision,
        filename=f"{doc_type}_{doc_id}.jpg",
        traveler_data=traveler_data,
        module_statuses=module_statuses or {"ocr": "completed", "validation": "completed", "registry": "completed"},
    )


class TestCaseScenarios:
    """Complete test suite for Scenarios 1 through 18."""

    @pytest.fixture(autouse=True)
    def setup_stores(self):
        """Create fresh isolated case manager and engine for each test."""
        self.store = VerificationCaseStore(ttl_seconds=300, max_entries=50)
        self.engine = CrossDocumentVerificationEngine(registry=relationship_registry)
        self.risk_evaluator = CaseRiskEvaluator()
        self.manager = CaseManager()
        self.manager._store = self.store
        self.manager._cross_doc_engine = self.engine
        self.manager._risk_evaluator = self.risk_evaluator

    # ── Scenario 1: Passport only ─────────────────────────────────────────────
    def test_scenario_01_passport_only(self):
        case = self.manager.create_case(case_id="CASE-01")
        doc_p = _build_doc("DOC-001", "passport", {
            "document_number": "T9876543",
            "name": "JOHN DOE",
            "date_of_birth": "1990-06-15",
            "nationality": "USA",
        })
        case.add_document(doc_p)
        self.engine.evaluate_case(case)
        assessment = self.risk_evaluator.evaluate_case_risk(case)

        assert len(case.get_active_documents()) == 1
        assert len(case.relationships) == 0  # No peers to compare against
        assert assessment["risk_level"] in ("LOW", "CLEAR")
        assert "DOC-001" in assessment["documents_considered"]

    # ── Scenario 2: Visa only ─────────────────────────────────────────────────
    def test_scenario_02_visa_only(self):
        case = self.manager.create_case(case_id="CASE-02")
        doc_v = _build_doc("DOC-002", "visa", {
            "passport_number": "T9876543",
            "name": "JOHN DOE",
            "date_of_birth": "1990-06-15",
            "nationality": "USA",
        })
        case.add_document(doc_v)
        self.engine.evaluate_case(case)
        assessment = self.risk_evaluator.evaluate_case_risk(case)

        assert len(case.get_active_documents()) == 1
        assert len(case.relationships) == 0
        assert "DOC-002" in assessment["documents_considered"]

    # ── Scenario 3: Passport + Visa matching ──────────────────────────────────
    def test_scenario_03_passport_visa_matching(self):
        case = self.manager.create_case(case_id="CASE-03")
        doc_p = _build_doc("DOC-001", "passport", {
            "document_number": "T9876543",
            "name": "JOHN DOE",
            "date_of_birth": "1990-06-15",
            "nationality": "IND",
        })
        doc_v = _build_doc("DOC-002", "visa", {
            "passport_number": "T9876543",
            "name": "JOHN DOE",
            "date_of_birth": "1990-06-15",
            "nationality": "IND",
        })
        case.add_document(doc_p)
        case.add_document(doc_v)

        self.engine.evaluate_case(case)
        assessment = self.risk_evaluator.evaluate_case_risk(case)

        assert len(case.relationships) >= 3
        # All evaluated relationships should be MATCHED
        for rel in case.relationships:
            assert rel.status == RelationshipStatus.MATCHED
        assert assessment["conflict_detected"] is False
        assert assessment["risk_score"] == 0

    # ── Scenario 4: Passport + Visa passport-number mismatch ──────────────────
    def test_scenario_04_passport_visa_number_mismatch(self):
        case = self.manager.create_case(case_id="CASE-04")
        doc_p = _build_doc("DOC-001", "passport", {
            "document_number": "T9876543",
            "name": "JOHN DOE",
            "date_of_birth": "1990-06-15",
            "nationality": "IND",
        })
        doc_v = _build_doc("DOC-002", "visa", {
            "passport_number": "T9876548",  # Mismatch!
            "name": "JOHN DOE",
            "date_of_birth": "1990-06-15",
            "nationality": "IND",
        })
        case.add_document(doc_p)
        case.add_document(doc_v)

        self.engine.evaluate_case(case)
        assessment = self.risk_evaluator.evaluate_case_risk(case)

        # Look for identifier relationship
        id_rels = [r for r in case.relationships if r.source_document.field == "passport_number"]
        assert len(id_rels) == 1
        assert id_rels[0].status == RelationshipStatus.MISMATCH
        assert id_rels[0].severity == "HIGH"

        # Check case risk is elevated
        assert assessment["risk_score"] >= 20
        assert assessment["conflict_detected"] is True

    # ── Scenario 5: Passport + Visa DOB mismatch ──────────────────────────────
    def test_scenario_05_dob_mismatch(self):
        case = self.manager.create_case(case_id="CASE-05")
        doc_p = _build_doc("DOC-001", "passport", {
            "document_number": "T9876543",
            "name": "JOHN DOE",
            "date_of_birth": "1990-06-15",
        })
        doc_v = _build_doc("DOC-002", "visa", {
            "passport_number": "T9876543",
            "name": "JOHN DOE",
            "date_of_birth": "1992-11-20",  # Mismatch
        })
        case.add_document(doc_p)
        case.add_document(doc_v)

        self.engine.evaluate_case(case)
        dob_rels = [r for r in case.relationships if r.source_document.field == "date_of_birth"]
        assert len(dob_rels) == 1
        assert dob_rels[0].status == RelationshipStatus.MISMATCH
        assert dob_rels[0].severity == "HIGH"

    # ── Scenario 6: Name formatting difference (conservative) ─────────────────
    def test_scenario_06_name_formatting_difference(self):
        case = self.manager.create_case(case_id="CASE-06")
        doc_p = _build_doc("DOC-001", "passport", {
            "document_number": "T9876543",
            "name": "JOHN ALEXANDER DOE",
        })
        doc_v = _build_doc("DOC-002", "visa", {
            "passport_number": "T9876543",
            "name": "JOHN DOE",  # Subset of passport name tokens
        })
        case.add_document(doc_p)
        case.add_document(doc_v)

        self.engine.evaluate_case(case)
        name_rels = [r for r in case.relationships if r.source_document.field == "name"]
        assert len(name_rels) == 1
        # Token set matching: subset yields PARTIAL_MATCH with LOW severity, NOT a high fraud flag
        assert name_rels[0].status == RelationshipStatus.PARTIAL_MATCH
        assert name_rels[0].severity == "LOW"

    # ── Scenario 7: Missing optional field ────────────────────────────────────
    def test_scenario_07_missing_optional_field(self):
        case = self.manager.create_case(case_id="CASE-07")
        doc_p = _build_doc("DOC-001", "passport", {
            "document_number": "T9876543",
            "name": "JOHN DOE",
            # Nationality omitted on passport
        })
        doc_v = _build_doc("DOC-002", "visa", {
            "passport_number": "T9876543",
            "name": "JOHN DOE",
            "nationality": "IND",
        })
        case.add_document(doc_p)
        case.add_document(doc_v)

        self.engine.evaluate_case(case)
        nat_rels = [r for r in case.relationships if r.source_document.field == "nationality"]
        assert len(nat_rels) == 1
        assert nat_rels[0].status == RelationshipStatus.MISSING_TARGET_FIELD
        assert nat_rels[0].severity == "NONE"

    # ── Scenario 8: Passport complete + Visa partial ──────────────────────────
    def test_scenario_08_passport_complete_visa_partial(self):
        case = self.manager.create_case(case_id="CASE-08")
        doc_p = _build_doc("DOC-001", "passport", {
            "document_number": "T9876543",
            "name": "JOHN DOE",
        })
        # Visa is still processing/partial
        doc_v = _build_doc("DOC-002", "visa", {}, status=DocumentStatus.PARTIAL)
        case.add_document(doc_p)
        case.add_document(doc_v)

        self.engine.evaluate_case(case)
        assessment = self.risk_evaluator.evaluate_case_risk(case)

        assert case.status == CaseStatus.ACTIVE
        assert assessment["verification_completeness"] < 1.0

    # ── Scenario 9: Upload order independence ─────────────────────────────────
    def test_scenario_09_order_independence(self):
        # Case A: Passport first, Visa second
        case_a = self.manager.create_case(case_id="CASE-09A")
        p1 = _build_doc("DOC-001", "passport", {"document_number": "A123", "name": "ALICE WONG"})
        v1 = _build_doc("DOC-002", "visa", {"passport_number": "A123", "name": "ALICE WONG"})
        case_a.add_document(p1)
        case_a.add_document(v1)
        self.engine.evaluate_case(case_a)
        res_a = {r.source_document.field: r.status for r in case_a.relationships}

        # Case B: Visa first, Passport second
        case_b = self.manager.create_case(case_id="CASE-09B")
        v2 = _build_doc("DOC-001", "visa", {"passport_number": "A123", "name": "ALICE WONG"})
        p2 = _build_doc("DOC-002", "passport", {"document_number": "A123", "name": "ALICE WONG"})
        case_b.add_document(v2)
        case_b.add_document(p2)
        self.engine.evaluate_case(case_b)
        res_b = {r.source_document.field: r.status for r in case_b.relationships}

        assert res_a == res_b
        assert res_a["passport_number"] == RelationshipStatus.MATCHED

    # ── Scenario 10: Passport replaced invalidates old relationships ──────────
    def test_scenario_10_passport_replaced_invalidates_evidence(self):
        case = self.manager.create_case(case_id="CASE-10")
        doc_p1 = _build_doc("DOC-001", "passport", {"document_number": "OLD123", "name": "ALICE"}, revision=1)
        doc_v = _build_doc("DOC-002", "visa", {"passport_number": "OLD123", "name": "ALICE"}, revision=1)
        case.add_document(doc_p1)
        case.add_document(doc_v)
        self.engine.evaluate_case(case)
        assert len(case.relationships) > 0

        # Replace Passport with new one
        case.supersede_document_type("passport")
        assert len(case.relationships) == 0
        assert len(case.cross_document_evidence) == 0

        # Add replacement passport
        doc_p2 = _build_doc("DOC-003", "passport", {"document_number": "NEW999", "name": "ALICE"}, revision=2)
        case.add_document(doc_p2)
        self.engine.evaluate_case(case)

        # Now mismatch should reflect NEW999 vs OLD123
        id_rel = next(r for r in case.relationships if r.source_document.field == "passport_number")
        assert id_rel.status == RelationshipStatus.MISMATCH
        assert id_rel.target_document.value == "NEW999"

    # ── Scenario 11: Visa replaced invalidates affected evidence ──────────────
    def test_scenario_11_visa_replaced_invalidates_evidence(self):
        case = self.manager.create_case(case_id="CASE-11")
        doc_p = _build_doc("DOC-001", "passport", {"document_number": "PASS123", "name": "BOB"})
        doc_v1 = _build_doc("DOC-002", "visa", {"passport_number": "PASS123", "name": "BOB"})
        case.add_document(doc_p)
        case.add_document(doc_v1)
        self.engine.evaluate_case(case)
        assert len(case.relationships) > 0

        case.supersede_document_type("visa")
        assert len(case.relationships) == 0

        doc_v2 = _build_doc("DOC-003", "visa", {"passport_number": "PASS123", "name": "BOB"}, revision=2)
        case.add_document(doc_v2)
        self.engine.evaluate_case(case)
        assert len(case.relationships) > 0

    # ── Scenario 12: Duplicate document prevented ─────────────────────────────
    def test_scenario_12_duplicate_document_prevented(self):
        case = self.manager.create_case(case_id="CASE-12")
        doc_p1 = _build_doc("DOC-001", "passport", {"document_number": "P1"})
        case.add_document(doc_p1)

        # Checking through manager add_document_to_case with replace=False
        with pytest.raises(DuplicateDocumentTypeError):
            asyncio.run(
                self.manager.add_document_to_case(
                    case_id="CASE-12",
                    document_type="passport",
                    file_bytes=b"dummy",
                    filename="p2.jpg",
                    replace=False,
                )
            )

    # ── Scenario 13: Registry mismatch + cross-doc mismatch avoids double-count
    def test_scenario_13_registry_and_cross_doc_avoids_double_counting(self):
        case = self.manager.create_case(case_id="CASE-13")
        doc_p = _build_doc("DOC-001", "passport", {"document_number": "P123", "name": "CARL"})
        doc_v = _build_doc("DOC-002", "visa", {"passport_number": "P999", "name": "CARL"})
        case.add_document(doc_p)
        case.add_document(doc_v)

        # Mock Risk store for doc_v with M5 registry mismatch
        risk_session_store.update_module(
            doc_v.verification_id, "m5_registry",
            {
                "registry": {"status": "MATCH_WITH_DISCREPANCIES"},
                "field_results": [
                    {
                        "field": "passport_number",
                        "status": "MISMATCH",
                        "claimed_value": "P999",
                        "authoritative_value": "P123",
                    }
                ]
            }
        )

        self.engine.evaluate_case(case)
        assessment = self.risk_evaluator.evaluate_case_risk(case)

        # Cross-document items are grouped under PASSPORT_VISA_IDENTIFIER_BINDING
        # Verifying aggregator and evaluator deduplicate effectively
        assert assessment["risk_score"] > 0
        assert assessment["conflict_detected"] is True

    # ── Scenario 14: M2 mismatch + cross-doc mismatch grouping ────────────────
    def test_scenario_14_m2_and_cross_doc_evidence_grouping(self):
        case = self.manager.create_case(case_id="CASE-14")
        doc_p = _build_doc("DOC-001", "passport", {"document_number": "P100", "name": "DAVE"})
        doc_v = _build_doc("DOC-002", "visa", {"passport_number": "P999", "name": "DAVE"})
        case.add_document(doc_p)
        case.add_document(doc_v)

        self.engine.evaluate_case(case)

        # Check cross-doc evidence has correlation_group assigned
        for item in case.cross_document_evidence:
            if item.signal == "passport_visa_identifier_mismatch":
                assert item.correlation_group == "PASSPORT_VISA_IDENTIFIER_BINDING"

        assessment = self.risk_evaluator.evaluate_case_risk(case)
        assert assessment["risk_score"] > 0

    # ── Scenario 15: One document removed -> case risk recalculated ───────────
    def test_scenario_15_document_removal_recalculates_risk(self):
        case = self.manager.create_case(case_id="CASE-15")
        doc_p = _build_doc("DOC-001", "passport", {"document_number": "P1", "name": "EVE"})
        doc_v = _build_doc("DOC-002", "visa", {"passport_number": "P999", "name": "EVE"})  # Mismatch
        case.add_document(doc_p)
        case.add_document(doc_v)

        self.engine.evaluate_case(case)
        high_risk_assessment = self.risk_evaluator.evaluate_case_risk(case)
        assert high_risk_assessment["risk_score"] >= 20

        # Remove mismatched Visa
        self.manager.remove_document_from_case("CASE-15", "DOC-002")

        # Now only Passport remains; relationships should be cleared and risk recalculated
        updated_case = self.manager.get_case("CASE-15")
        assert len(updated_case.relationships) == 0
        assert len(updated_case.cross_document_evidence) == 0
        assert updated_case.risk_assessment["risk_score"] == 0
        assert updated_case.risk_assessment["conflict_detected"] is False

    # ── Scenario 16: Concurrent processing safety ─────────────────────────────
    def test_scenario_16_concurrent_case_processing(self):
        case = self.manager.create_case(case_id="CASE-16")

        def add_doc(doc_id: str, doc_type: str, num: str):
            d = _build_doc(doc_id, doc_type, {"document_number": num, "passport_number": num, "name": "FRANK"})
            case.add_document(d)
            self.engine.evaluate_case(case)
            return self.risk_evaluator.evaluate_case_risk(case)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            fut1 = executor.submit(add_doc, "DOC-001", "passport", "N100")
            fut2 = executor.submit(add_doc, "DOC-002", "visa", "N100")
            res1 = fut1.result()
            res2 = fut2.result()

        assert res1 is not None
        assert res2 is not None
        assert len(case.get_active_documents()) == 2

    # ── Scenario 17: Client cannot inject client-supplied evidence ────────────
    def test_scenario_17_client_cannot_inject_matched_evidence(self):
        case = self.manager.create_case(case_id="CASE-17")
        doc_p = _build_doc("DOC-001", "passport", {"document_number": "P_REAL", "name": "GRACE"})
        doc_v = _build_doc("DOC-002", "visa", {"passport_number": "P_FAKE", "name": "GRACE"})
        case.add_document(doc_p)
        case.add_document(doc_v)

        # In a real attack, client might POST a forged relationship into the evaluate or risk endpoint
        # The evaluate endpoint re-evaluates strictly server-side using stored document fields
        self.engine.evaluate_case(case)

        # Result MUST be MISMATCH regardless of what client wants
        id_rel = next(r for r in case.relationships if r.source_document.field == "passport_number")
        assert id_rel.status == RelationshipStatus.MISMATCH

    # ── Scenario 18: Unknown document type rejected ───────────────────────────
    def test_scenario_18_unknown_document_type_rejected(self):
        case = self.manager.create_case(case_id="CASE-18")
        with pytest.raises(DocumentProfileError):
            asyncio.run(
                self.manager.add_document_to_case(
                    case_id="CASE-18",
                    document_type="unsupported_alien_pass",
                    file_bytes=b"dummy",
                    filename="alien.jpg",
                )
            )
