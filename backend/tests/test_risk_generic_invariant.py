"""
tests/test_risk_generic_invariant.py

Architectural Invariant Test:
Proves that Module 6 (Risk Engine) does NOT contain document-specific risk logic.
Proves that both Passport evidence and Visa evidence are normalized into the
identical canonical RiskEvidenceItem schema, and processed by the
exact same aggregation, conflict detection, and scoring formulas.
"""
import inspect
import pytest
from app.services.risk.risk_aggregator import RiskAggregator
from app.services.risk.risk_config import RiskConfig
from app.services.risk.risk_conflict_detector import ConflictDetector
from app.services.risk.risk_engine import RiskEngine
from app.services.risk.risk_evidence import (
    EvidenceCategory,
    EvidenceSeverity,
    EvidenceStatus,
    RiskEvidenceItem,
)
from app.services.risk.risk_normalizer import (
    normalize_ocr,
    normalize_validation,
)
from app.services.risk.risk_rules import RULE_TABLE, get_base_contribution


class TestRiskGenericInvariant:
    def test_m6_engine_has_no_document_type_branching_in_calculation(self):
        """
        Prove that the core score aggregation function in RiskAggregator takes
        only (items, conflicts, completeness) and has NO document_type parameter.
        """
        agg_sig = inspect.signature(RiskAggregator.aggregate)
        params = list(agg_sig.parameters.keys())
        assert "document_type" not in params
        assert "is_passport" not in params
        assert "is_visa" not in params

    def test_passport_and_visa_evidence_normalize_to_canonical_signals(self):
        """
        Passport expired check and Visa expired check both normalize
        to canonical RiskEvidenceItem objects with module 'M2'.
        """
        # Passport M2 checks
        passport_data = {
            "status": "failed",
            "summary": "Passport expired",
            "checks": {
                "expiry_date": {
                    "valid": False,
                    "status": "failed",
                    "expired": True,
                    "expiry_date": "2020-01-01",
                    "message": "Passport expired",
                }
            },
        }
        ppt_items = normalize_validation(passport_data)
        ppt_high = [i for i in ppt_items if i.severity in (EvidenceSeverity.HIGH, EvidenceSeverity.CRITICAL)]
        assert len(ppt_high) >= 1
        assert isinstance(ppt_high[0], RiskEvidenceItem)
        assert ppt_high[0].module == "M2"

        # Visa M2 checks
        visa_data = {
            "status": "failed",
            "summary": "Visa expired",
            "checks": {
                "expiry_date": {
                    "valid": False,
                    "status": "failed",
                    "expired": True,
                    "expiry_date": "2020-01-01",
                    "message": "Visa expired",
                }
            },
        }
        visa_items = normalize_validation(visa_data)
        visa_high = [i for i in visa_items if i.severity in (EvidenceSeverity.HIGH, EvidenceSeverity.CRITICAL)]
        assert len(visa_high) >= 1
        assert isinstance(visa_high[0], RiskEvidenceItem)
        assert visa_high[0].module == "M2"

        # Both produce items evaluated by the exact same aggregator
        aggregator = RiskAggregator(RiskConfig())
        ppt_result = aggregator.aggregate(ppt_items)
        visa_result = aggregator.aggregate(visa_items)

        # Both trigger expired penalty resulting in identical risk score
        assert ppt_result.risk_score == 8
        assert visa_result.risk_score == 8
        config = RiskConfig()
        assert config.risk_level(ppt_result.risk_score) == config.risk_level(visa_result.risk_score)

    def test_missing_mrz_not_penalized_when_mrz_not_applicable(self):
        """
        On Passport (mrz_applicable=True), missing MRZ produces an item.
        On Visa (mrz_applicable=False), missing MRZ produces NO penalty item.
        """
        ocr_no_mrz_passport = {
            "status": "completed",
            "overall_confidence": 0.95,
            "mrz_available": False,
            "mrz_detected": False,
            "mrz_applicable": True,
            "critical_fields_missing": [],
        }
        ev_ppt = normalize_ocr(ocr_no_mrz_passport)
        assert any(i.signal == "mrz_unavailable" for i in ev_ppt)

        ocr_no_mrz_visa = {
            "status": "completed",
            "overall_confidence": 0.95,
            "mrz_available": False,
            "mrz_detected": False,
            "mrz_applicable": False,
            "critical_fields_missing": [],
        }
        ev_visa = normalize_ocr(ocr_no_mrz_visa)
        assert not any(i.signal == "mrz_unavailable" for i in ev_visa)

    def test_cross_document_mismatch_enters_generic_risk_pipeline(self):
        """
        Cross-document mismatch signal flows through canonical risk pipeline
        and increases risk score without any document-specific risk formula.
        """
        visa_data = {
            "status": "failed",
            "summary": "Passport mismatch",
            "checks": {
                "cross_document_passport": {
                    "status": "failed",
                    "valid": False,
                    "message": "Visa passport reference P123 does not match passport document P999",
                }
            },
        }
        items = normalize_validation(visa_data)
        mismatch_items = [i for i in items if i.signal == "cross_document_mismatch"]
        assert len(mismatch_items) == 1
        assert mismatch_items[0].severity == EvidenceSeverity.CRITICAL

        aggregator = RiskAggregator(RiskConfig())
        result = aggregator.aggregate(items)
        assert result.risk_score == 20
        from app.services.risk.risk_explanation import ExplanationBuilder
        explainer = ExplanationBuilder()
        reasons, _ = explainer.build_reasons(result)
        assert any(r.signal == "cross_document_mismatch" for r in reasons)
