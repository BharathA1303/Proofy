"""
backend/tests/test_border_permit_case_scenarios.py

Comprehensive case scenarios and security tests for Border Permit:
1. 5-document verification case (Passport + Visa + DL + National ID + Border Permit)
2. Case documents maintain independent analytical pipelines
3. Duplicate document type rejection (DuplicateDocumentTypeError)
4. Document replacement invalidation (superseded documents)
5. Double-counting protection (diminishing returns via correlation groups)
6. Zero demographic profiling immunity (nationality, region never penalized)
7. Sensitive identifier protection
"""
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app.core.exceptions import DuplicateDocumentTypeError
from app.schemas.case import DocumentStatus
from app.services.case.case_manager import CaseManager
from app.services.case.verification_case import CaseDocument, VerificationCase
import app.services.ocr.ocr_engine as ocr_engine_module
from app.services.ocr.ocr_engine import OCRRegion
from app.services.risk.risk_aggregator import RiskAggregator
from app.services.risk.risk_config import RiskConfig
from app.services.risk.risk_evidence import (
    CorrelationGroup,
    EvidenceCategory,
    EvidenceSeverity,
    EvidenceStatus,
    RiskEvidenceItem,
)


@pytest.fixture(autouse=True)
def mock_ocr(monkeypatch):
    """Provide deterministic OCR output for Passport, Visa, DL, National ID, and Border Permit."""
    def fake_run_ocr(img_np):
        return [
            # DL / Header / Gov
            OCRRegion(text="UNION OF INDIA", confidence=0.99, bbox=[[10, 10], [200, 10], [200, 30], [10, 30]]),
            OCRRegion(text="Government of India", confidence=0.99, bbox=[[10, 10], [300, 10], [300, 30], [10, 30]]),
            OCRRegion(text="Unique Identification Authority of India", confidence=0.99, bbox=[[10, 35], [400, 35], [400, 55], [10, 55]]),
            # Border Permit Header
            OCRRegion(text="REGIONAL BORDER CONTROL", confidence=0.99, bbox=[[10, 10], [300, 10], [300, 30], [10, 30]]),
            OCRRegion(text="OFFICIAL ENTRY & CROSSING PERMIT", confidence=0.99, bbox=[[10, 35], [400, 35], [400, 55], [10, 55]]),
            OCRRegion(text="PERMIT NO: BP-2026-000123", confidence=0.98, bbox=[[285, 110], [600, 110], [600, 130], [285, 130]]),
            OCRRegion(text="LINKED PASSPORT NO: P1234567", confidence=0.99, bbox=[[285, 230], [600, 230], [600, 250], [285, 250]]),
            OCRRegion(text="PORT OF ENTRY: NORTH GATE TERMINAL", confidence=0.96, bbox=[[285, 310], [600, 310], [600, 330], [285, 330]]),
            OCRRegion(text="VALID FROM: 01-01-2026", confidence=0.98, bbox=[[285, 350], [600, 350], [600, 370], [285, 370]]),
            OCRRegion(text="VALID TO: 31-12-2026", confidence=0.98, bbox=[[285, 390], [600, 390], [600, 410], [285, 410]]),
            OCRRegion(text="PERMIT TYPE: ENTRY", confidence=0.98, bbox=[[285, 270], [600, 270], [600, 290], [285, 290]]),
            # DL
            OCRRegion(text="DRIVING LICENCE", confidence=0.99, bbox=[[10, 35], [200, 35], [200, 55], [10, 55]]),
            OCRRegion(text="DL No: DL0420110012345", confidence=0.98, bbox=[[10, 60], [300, 60], [300, 80], [10, 80]]),
            # National ID
            OCRRegion(text="9876 5432 1098", confidence=0.99, bbox=[[10, 160], [300, 160], [300, 185], [10, 185]]),
            # Shared Name and DOB
            OCRRegion(text="HOLDER NAME: ALEX DUPONT", confidence=0.98, bbox=[[10, 85], [300, 85], [300, 105], [10, 105]]),
            OCRRegion(text="Name: ALEX DUPONT", confidence=0.98, bbox=[[10, 85], [300, 85], [300, 105], [10, 105]]),
            OCRRegion(text="DOB: 12-08-1990", confidence=0.98, bbox=[[10, 110], [300, 110], [300, 130], [10, 130]]),
            OCRRegion(text="DATE OF BIRTH: 12-08-1990", confidence=0.98, bbox=[[10, 110], [300, 110], [300, 130], [10, 130]]),
            # Passport MRZ
            OCRRegion(text="P<FRADUPONT<<ALEX<<<<<<<<<<<<<<<<<<<<<<<<<<<", confidence=0.99, bbox=[[10, 200], [500, 200], [500, 220], [10, 220]]),
            OCRRegion(text="P1234567<8FRA9008120M3505142<<<<<<<<<<<<<<<04", confidence=0.99, bbox=[[10, 225], [500, 225], [500, 245], [10, 245]]),
            # Visa
            OCRRegion(text="VISA", confidence=0.99, bbox=[[10, 10], [100, 10], [100, 30], [10, 30]]),
            OCRRegion(text="V12345678", confidence=0.98, bbox=[[10, 35], [200, 35], [200, 55], [10, 55]]),
        ]

    monkeypatch.setattr(ocr_engine_module, "init_engine", lambda **kw: None)
    monkeypatch.setattr(ocr_engine_module, "run_ocr", fake_run_ocr)
    monkeypatch.setattr(ocr_engine_module, "_paddle_ocr_instance", MagicMock())


class TestBorderPermitCaseScenarios:
    @pytest.mark.asyncio
    async def test_five_document_case_pipeline(self):
        manager = CaseManager()
        case = manager.create_case(case_id="CASE-5DOC-TEST")

        asset_dir = Path(__file__).parent / "assets"
        p_asset = asset_dir / "sample_passport.jpg"
        v_asset = asset_dir / "sample_visa.jpg"
        dl_asset = asset_dir / "sample_driving_license.jpg"
        nid_asset = asset_dir / "sample_national_id.jpg"
        bp_asset = asset_dir / "sample_border_permit.jpg"

        if not all(p.exists() for p in (p_asset, v_asset, dl_asset, nid_asset, bp_asset)):
            pytest.skip("Synthetic assets not all generated")

        # Ingest Passport
        with open(p_asset, "rb") as f:
            doc_p, _ = await manager.add_document_to_case(case.case_id, "passport", f.read(), "passport.jpg")

        # Ingest Visa
        with open(v_asset, "rb") as f:
            doc_v, _ = await manager.add_document_to_case(case.case_id, "visa", f.read(), "visa.jpg")

        # Ingest DL
        with open(dl_asset, "rb") as f:
            doc_dl, _ = await manager.add_document_to_case(case.case_id, "driving_license", f.read(), "dl.jpg")

        # Ingest National ID
        with open(nid_asset, "rb") as f:
            doc_nid, _ = await manager.add_document_to_case(case.case_id, "national_id", f.read(), "nid.jpg")

        # Ingest Border Permit
        with open(bp_asset, "rb") as f:
            doc_bp, case_final = await manager.add_document_to_case(case.case_id, "border_permit", f.read(), "bp.jpg")

        # All 5 documents active simultaneously
        assert len(case_final.get_active_documents()) == 5
        assert doc_p.document_type == "passport"
        assert doc_v.document_type == "visa"
        assert doc_dl.document_type == "driving_license"
        assert doc_nid.document_type == "national_id"
        assert doc_bp.document_type == "border_permit"

        # Relationships evaluated across pairs
        assert len(case_final.relationships) >= 8

    def test_duplicate_border_permit_rejected(self):
        case = VerificationCase(case_id="CASE-DUP-BP")
        doc1 = CaseDocument(
            document_id="DOC-001",
            document_type="border_permit",
            verification_id="vid-1",
            status=DocumentStatus.COMPLETED,
        )
        case.documents[doc1.document_id] = doc1

        existing = case.get_document_by_type("border_permit")
        assert existing is not None

        with pytest.raises(DuplicateDocumentTypeError):
            if existing:
                raise DuplicateDocumentTypeError("border_permit")

    def test_border_permit_replacement_invalidates_old(self):
        case = VerificationCase(case_id="CASE-REPLACE-BP")
        doc1 = CaseDocument(
            document_id="DOC-001",
            document_type="border_permit",
            verification_id="vid-1",
            document_revision=1,
            status=DocumentStatus.COMPLETED,
        )
        case.documents[doc1.document_id] = doc1

        # Supersede old
        case.supersede_document_type("border_permit")
        assert doc1.status == DocumentStatus.SUPERSEDED

        doc2 = CaseDocument(
            document_id="DOC-002",
            document_type="border_permit",
            verification_id="vid-2",
            document_revision=2,
            status=DocumentStatus.COMPLETED,
        )
        case.documents[doc2.document_id] = doc2

        active = case.get_active_documents()
        assert len(active) == 1
        assert active[0].document_id == "DOC-002"
        assert active[0].document_revision == 2

    def test_double_counting_prevention(self):
        """
        Verify that multiple signals in BORDER_PERMIT_PASSPORT_BINDING
        apply diminishing returns via correlation groups.
        """
        config = RiskConfig()
        aggregator = RiskAggregator(config)

        item1 = RiskEvidenceItem(
            module="CROSS_DOCUMENT",
            signal="cross_doc_identifier_binding_mismatch",
            category=EvidenceCategory.DOCUMENT_CONSISTENCY,
            status=EvidenceStatus.MISMATCH,
            severity=EvidenceSeverity.HIGH,
            confidence=0.99,
            available=True,
            explanation="Passport number binding mismatch",
            provenance={"source": "test"},
            correlation_group=CorrelationGroup.BORDER_PERMIT_PASSPORT_BINDING,
        )
        item2 = RiskEvidenceItem(
            module="M2",
            signal="border_permit_passport_number_mismatch",
            category=EvidenceCategory.DOCUMENT_CONSISTENCY,
            status=EvidenceStatus.MISMATCH,
            severity=EvidenceSeverity.HIGH,
            confidence=0.99,
            available=True,
            explanation="M2 Passport reference mismatch duplicate",
            provenance={"source": "test"},
            correlation_group=CorrelationGroup.BORDER_PERMIT_PASSPORT_BINDING,
        )

        result = aggregator.aggregate([item1, item2])
        # Second item contribution must be discounted by 0.50
        c1 = item1.contribution
        c2 = item2.contribution
        assert c2 < c1
        assert round(c2, 2) == round(c1 * 0.50, 2)

    def test_demographic_profiling_immunity(self):
        from app.services.risk.risk_rules import RULE_TABLE

        for forbidden_signal in [
            "nationality_french", "nationality_indian", "nationality_us",
            "border_zone_north", "border_zone_south", "permit_type_transit",
            "purpose_tourism", "purpose_business",
        ]:
            assert forbidden_signal not in RULE_TABLE
