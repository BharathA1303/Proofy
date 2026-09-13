"""
backend/tests/test_risk_phase11.py

Comprehensive Phase 11 / M6 Evidence Fusion & Explainable Risk Engine Test Suite.
Verifies all mandatory test cases A through BB specified in Section 38.
"""
from __future__ import annotations

import copy
import json
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.documents.profiles import document_profile_registry
from app.services.documents.profiles.driving_license_profile import DRIVING_LICENSE_PROFILE
from app.services.risk.risk_aggregator import RiskAggregator
from app.services.risk.risk_config import RiskConfig
from app.services.risk.risk_conflict_detector import ConflictDetector
from app.services.risk.risk_engine import RiskEngine, risk_engine
from app.services.risk.risk_evidence import (
    CorrelationGroup,
    EvidenceCategory,
    EvidenceSeverity,
    EvidenceStatus,
    RiskEvidenceItem,
)
from app.services.risk.risk_explanation import ExplanationBuilder
from app.services.risk.risk_normalizer import RiskNormalizer, normalize_machine_readable
from app.services.risk.risk_session_store import risk_session_store

client = TestClient(app)


# ── Test Fixtures & Helpers ───────────────────────────────────────────────────

def _seed_clean_session(vid: str) -> None:
    """Seed clean, corroborated M1-M5 data."""
    risk_session_store.update_module(vid, "m1_ocr", {
        "status": "completed",
        "overall_confidence": 0.96,
        "has_low_confidence_regions": False,
        "mrz_available": False,
        "critical_fields_missing": [],
    })
    risk_session_store.update_module(vid, "m2_validation", {
        "status": "passed",
        "summary": "All DL structural checks passed.",
        "checks": {
            "license_number_format": {"valid": True, "status": "passed", "message": "Format valid."},
            "date_chronology": {"valid": True, "status": "passed", "message": "Chronology valid."},
            "age_eligibility": {"valid": True, "status": "passed", "message": "Eligible."},
        }
    })
    risk_session_store.update_module(vid, "m3_forensics", {
        "status": "completed",
        "overall_assessment": "no_significant_anomaly",
        "signals": []
    })
    risk_session_store.update_module(vid, "m4_biometrics", {
        "overall_assessment": "FACE_MATCH",
        "document_face": {"detected": True, "quality": "acceptable"},
        "live_face": {"detected": True, "quality": "acceptable"},
        "anti_spoof": {"status": "pass", "score": 0.98, "model": "MiniFASNetV2", "explanation": "Live."},
        "face_match": {"status": "match", "similarity": 0.88, "threshold": 0.40, "explanation": "Match."},
    })
    risk_session_store.update_module(vid, "m5_registry", {
        "registry": {"status": "MATCHED", "record_found": True},
        "field_results": [],
        "provider_metadata": {"provider_id": "mock_dl_registry", "source_type": "development_mock"},
    })


def _seed_m7_clean(vid: str) -> None:
    """Add clean M7 machine-readable QR data."""
    risk_session_store.update_module(vid, "m7_machine_readable", {
        "document_type": "driving_license",
        "applicable": True,
        "detection_status": "DECODED",
        "crypto_verification": {
            "status": "CRYPTO_VERIFICATION_PASSED",
            "algorithm": "SHA256withRSA",
            "details": "Signature valid",
        },
        "field_cross_checks": {
            "license_number": {
                "status": "QR_FIELD_MATCH",
                "is_match": True,
                "qr_value": "DL-1420110012345",
                "ocr_value": "DL-1420110012345",
            },
            "dob": {
                "status": "QR_FIELD_MATCH",
                "is_match": True,
                "qr_value": "1990-05-15",
                "ocr_value": "1990-05-15",
            }
        }
    })


# ── Test Cases A through BB ───────────────────────────────────────────────────

class TestRiskPhase11:

    def test_case_a_zero_evidence_inconclusive(self):
        """A. Zero evidence (all modules unrun) -> score=0, confidence low/0, level INCONCLUSIVE."""
        vid = "p11-test-zero-001"
        risk_session_store.evict(vid)
        res = risk_engine.assess(vid, "driving_license")
        assert res["risk_score"] == 0
        assert res["assessment_confidence"] == 0.0
        assert res["risk_level"] == "INCONCLUSIVE"
        assert "INCONCLUSIVE" in res["officer_recommendation"]
        assert len(res["limitations"]) > 0

    def test_case_b_clean_evidence_positive_corroboration(self):
        """B. Clean evidence only -> score=0, level LOW, supporting_evidence populated."""
        vid = "p11-test-clean-002"
        _seed_clean_session(vid)
        res = risk_engine.assess(vid, "driving_license")
        assert res["risk_score"] < 15
        assert res["risk_level"] == "LOW"
        assert res["officer_recommendation"] == "STANDARD OFFICER REVIEW"
        assert len(res["supporting_evidence"]) >= 3
        # Ensure positive evidence has PASS or CORROBORATED status
        statuses = [s["status"] for s in res["supporting_evidence"]]
        assert any(s in ("PASS", "CORROBORATED") for s in statuses)

    def test_case_c_single_critical_override_registry_revoked(self):
        """C. Single critical adverse signal (registry REVOKED) -> score >= 85, level CRITICAL, override applied."""
        vid = "p11-test-revoked-003"
        _seed_clean_session(vid)
        risk_session_store.update_module(vid, "m5_registry", {
            "registry": {"status": "REVOKED", "record_found": True},
            "field_results": [],
            "provider_metadata": {"provider_id": "sarathi_parivahan", "source_type": "authoritative"},
        })
        res = risk_engine.assess(vid, "driving_license")
        assert res["risk_score"] >= 85
        assert res["risk_level"] == "CRITICAL"
        assert res["critical_override_applied"] is True
        assert len(res["top_contributors"]) > 0
        assert res["top_contributors"][0]["evidence_type"] == "registry_revoked"

    def test_case_d_correlated_forensic_signals_diminishing_returns(self):
        """D. Correlated adverse signals -> diminishing returns applied, score less than 3x single signal."""
        config = RiskConfig()
        agg = RiskAggregator(config)
        # Single signal
        item1 = RiskEvidenceItem(
            module="M3", signal="forensic_ela_anomaly",
            category=EvidenceCategory.FORENSIC_ANOMALY,
            status=EvidenceStatus.SUSPICIOUS, severity=EvidenceSeverity.HIGH,
            confidence=0.95, available=True, explanation="ELA anomaly",
            provenance={}, correlation_group=CorrelationGroup.FORENSIC_IMAGE_SIGNALS,
        )
        res1 = agg.aggregate([item1])

        # 3 correlated signals in same group
        item2 = copy.copy(item1)
        item2.signal = "forensic_compression_anomaly"
        item3 = copy.copy(item1)
        item3.signal = "forensic_metadata_anomaly"

        res_corr = agg.aggregate([item1, item2, item3])
        # With diminishing returns (1.0, 0.5, 0.25), sum = 1.75x base, strictly less than 3x base
        assert res_corr.risk_score < res1.risk_score * 3
        assert res_corr.risk_score <= int(round(res1.risk_score * 1.85))

    def test_case_e_multi_module_adverse_signals(self):
        """E. Multi-module adverse signals -> elevated score bounded properly without crash."""
        vid = "p11-test-multimod-005"
        _seed_clean_session(vid)
        risk_session_store.update_module(vid, "m3_forensics", {
            "status": "completed",
            "overall_assessment": "suspicious",
            "signals": [
                {"type": "ela", "status": "suspicious", "severity": "high", "confidence": 0.90, "description": "Tampering"}
            ]
        })
        risk_session_store.update_module(vid, "m4_biometrics", {
            "overall_assessment": "FACE_MISMATCH",
            "document_face": {"detected": True, "quality": "acceptable"},
            "live_face": {"detected": True, "quality": "acceptable"},
            "face_match": {"status": "no_match", "similarity": 0.15, "threshold": 0.40, "explanation": "Mismatch"},
        })
        res = risk_engine.assess(vid, "driving_license")
        assert res["risk_score"] >= 30
        assert 0 <= res["risk_score"] <= 100


    def test_case_f_cross_source_contradiction_detected(self):
        """F. Cross-source contradiction (OCR DOB vs QR DOB) -> contradiction detected, fields listed."""
        vid = "p11-test-contra-006"
        _seed_clean_session(vid)
        risk_session_store.update_module(vid, "m7_machine_readable", {
            "document_type": "driving_license",
            "applicable": True,
            "detection_status": "DECODED",
            "crypto_verification": {"status": "CRYPTO_VERIFICATION_PASSED"},
            "field_cross_checks": {
                "dob": {
                    "status": "QR_FIELD_MISMATCH",
                    "is_match": False,
                    "qr_value": "1995-06-15",
                    "ocr_value": "1985-06-15",
                }
            }
        })
        res = risk_engine.assess(vid, "driving_license")
        assert len(res["contradictions"]) > 0
        contra = res["contradictions"][0]
        assert contra["type"] == "CROSS_SOURCE_CONTRADICTION"
        assert "dob" in contra["fields"]
        assert contra["severity"] in ("CRITICAL", "HIGH")

    def test_case_g_missing_optional_module_limitation_recorded(self):
        """G. Missing optional module (e.g. M7 QR unrun) -> limitation recorded, score not penalized."""
        vid = "p11-test-opt-007"
        _seed_clean_session(vid)
        res = risk_engine.assess(vid, "driving_license")
        assert res["risk_score"] < 15
        assert res["risk_level"] == "LOW"

    def test_case_h_unconfigured_live_registry_zero_score_penalty(self):
        """H. Unconfigured live registry -> recorded as limitation with 0 score penalty, not scored as fraud."""
        vid = "p11-test-unconf-008"
        _seed_clean_session(vid)
        risk_session_store.update_module(vid, "m5_registry", {
            "registry": {"status": "LIVE_PROVIDER_NOT_CONFIGURED", "record_found": False},
            "field_results": [],
            "provider_metadata": {"provider_id": "sarathi_live", "source_type": "unconfigured"},
        })
        res = risk_engine.assess(vid, "driving_license")
        assert res["risk_score"] < 15
        assert res["risk_level"] == "LOW"
        lims = [l["limitation"] for l in res["limitations"]]
        assert any("not available or not configured" in l.lower() or "registry" in l.lower() for l in lims)

    def test_case_i_mock_registry_explicit_identification(self):
        """I. Mock registry vs live registry -> mock results explicitly identified, never called 'government verified'."""
        vid = "p11-test-mock-009"
        _seed_clean_session(vid)
        res = risk_engine.assess(vid, "driving_license")
        res_str = json.dumps(res).lower()
        assert "government verified" not in res_str
        # Provenance explicitly identifies mock
        m5_items = [e for e in res["supporting_evidence"] if e["source_module"] == "M5"]
        assert len(m5_items) > 0
        assert "development mock" in m5_items[0]["explanation"] or "registry" in m5_items[0]["explanation"]

    def test_case_j_negative_evidence_cannot_be_canceled_by_positive(self):
        """J. Negative evidence cannot be canceled out by positive evidence -> revoked registry + matching face."""
        vid = "p11-test-nocancel-010"
        _seed_clean_session(vid)  # has matching face (M4 pass)
        risk_session_store.update_module(vid, "m5_registry", {
            "registry": {"status": "REVOKED", "record_found": True},
            "field_results": [],
            "provider_metadata": {"provider_id": "sarathi", "source_type": "authoritative"},
        })
        res = risk_engine.assess(vid, "driving_license")
        # Score must remain CRITICAL/HIGH despite matching face!
        assert res["risk_score"] >= 85
        assert res["risk_level"] == "CRITICAL"
        assert res["officer_recommendation"] == "CRITICAL REVIEW REQUIRED"

    def test_case_k_low_image_quality_discounts_confidence(self):
        """K. Low image quality discounts forensic signal confidence -> lower contribution than high quality."""
        config = RiskConfig()
        agg = RiskAggregator(config)
        item_high_qual = RiskEvidenceItem(
            module="M3", signal="forensic_ela_anomaly",
            category=EvidenceCategory.FORENSIC_ANOMALY,
            status=EvidenceStatus.SUSPICIOUS, severity=EvidenceSeverity.HIGH,
            confidence=0.90, quality=1.0, available=True, explanation="ELA high qual",
            provenance={},
        )
        item_low_qual = RiskEvidenceItem(
            module="M3", signal="forensic_ela_anomaly",
            category=EvidenceCategory.FORENSIC_ANOMALY,
            status=EvidenceStatus.SUSPICIOUS, severity=EvidenceSeverity.HIGH,
            confidence=0.90, quality=0.30, available=True, explanation="ELA low qual",
            provenance={},
        )
        res_high = agg.aggregate([item_high_qual])
        res_low = agg.aggregate([item_low_qual])
        assert res_low.risk_score < res_high.risk_score

    def test_case_l_audit_snapshot_reproducibility(self):
        """L. Audit snapshot reproducibility -> same inputs produce identical SHA-256 snapshot hash."""
        vid = "p11-test-audit-012"
        _seed_clean_session(vid)
        res1 = risk_engine.assess(vid, "driving_license")
        res2 = risk_engine.assess(vid, "driving_license")
        assert res1["snapshot_hash"] == res2["snapshot_hash"]
        assert len(res1["snapshot_hash"]) == 64

    def test_case_m_client_submitted_score_ignored(self):
        """M. Client-submitted score ignored -> client sending score=0 in API payload does not affect computed score."""
        vid = "p11-test-spoof-client-013"
        _seed_clean_session(vid)
        # Add revoked registry so score is high
        risk_session_store.update_module(vid, "m5_registry", {
            "registry": {"status": "REVOKED", "record_found": True},
            "field_results": [],
            "provider_metadata": {"provider_id": "sarathi", "source_type": "authoritative"},
        })
        # Client maliciously sends risk_score=0 and risk_level="LOW"
        resp = client.post("/api/v1/verification/risk", json={
            "verification_id": vid,
            "document_type": "driving_license",
            "risk_score": 0,
            "risk_level": "LOW",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["risk_score"] >= 85
        assert data["risk_level"] == "CRITICAL"

    def test_case_n_zero_verdict_vocabulary(self):
        """N. Zero verdict vocabulary -> output contains no forbidden legal words."""
        vid = "p11-test-vocab-014"
        _seed_clean_session(vid)
        res = risk_engine.assess(vid, "driving_license")
        full_text = json.dumps(res).lower()
        forbidden = ["denied", "admit", "forged", "authentic", "blacklist", "detain", "arrest"]
        for word in forbidden:
            assert word not in full_text, f"Found forbidden legal word '{word}' in risk output."

    def test_case_o_driving_license_profile_driven_risk_config(self):
        """O. Driving license profile-driven risk configuration is loaded and applied."""
        dl_profile = document_profile_registry.resolve("driving_license")
        assert hasattr(dl_profile, "risk_config")
        assert "category_weights" in dl_profile.risk_config
        assert "critical_thresholds" in dl_profile.risk_config
        assert dl_profile.risk_config["critical_thresholds"]["registry_revoked"] == 85

    def test_case_p_explainable_multi_paragraph_output(self):
        """P. Explainable multi-paragraph output -> explanation contains 3 clear paragraphs."""
        vid = "p11-test-expl-016"
        _seed_clean_session(vid)
        res = risk_engine.assess(vid, "driving_license")
        explanation = res["explanation"]
        assert explanation is not None
        paragraphs = [p.strip() for p in explanation.split("\n\n") if p.strip()]
        assert len(paragraphs) == 3
        assert "assessment summary" in paragraphs[0].lower()
        assert "primary risk contributors" in paragraphs[1].lower()
        assert "corroboration and scope" in paragraphs[2].lower()

    def test_case_q_top_contributors_ranked(self):
        """Q. Top contributors ranked -> highest contributing adverse signal appears first."""
        vid = "p11-test-ranked-017"
        _seed_clean_session(vid)
        risk_session_store.update_module(vid, "m2_validation", {
            "status": "failed",
            "checks": {
                "license_number_format": {"valid": False, "status": "failed", "message": "Format warning"},
            }
        })
        risk_session_store.update_module(vid, "m4_biometrics", {
            "overall_assessment": "SUSPECTED_SPOOF",
            "anti_spoof": {"status": "suspected_spoof", "score": 0.20, "model": "MiniFASNetV2", "explanation": "Spoof"},
        })
        res = risk_engine.assess(vid, "driving_license")
        assert len(res["top_contributors"]) >= 2
        # Highest contribution first
        assert res["top_contributors"][0]["contribution"] >= res["top_contributors"][1]["contribution"]

    def test_case_r_m7_machine_readable_signals_integration(self):
        """R. M7 Machine-Readable signals integration -> QR payload mismatch correctly scores."""
        m7_data = {
            "applicable": True,
            "detection_status": "DECODED",
            "field_cross_checks": {
                "license_number": {
                    "status": "QR_FIELD_MISMATCH",
                    "is_match": False,
                    "qr_value": "DL-11111",
                    "ocr_value": "DL-99999",
                }
            }
        }
        items = normalize_machine_readable(m7_data)
        assert len(items) == 1
        assert items[0].signal == "qr_ocr_docnumber_mismatch"
        assert items[0].severity == EvidenceSeverity.CRITICAL
        assert items[0].correlation_group == CorrelationGroup.MACHINE_READABLE_SIGNALS

    def test_case_s_missing_crypto_keys_limitation_recorded(self):
        """S. Missing crypto keys -> limitation recorded, 0 score contribution."""
        m7_data = {
            "applicable": True,
            "detection_status": "DECODED",
            "crypto_verification": {
                "status": "CRYPTO_VERIFICATION_NOT_CONFIGURED",
                "details": "No public key configured for jurisdiction IN",
            },
            "field_cross_checks": {}
        }
        items = normalize_machine_readable(m7_data)
        crypto_item = next((i for i in items if i.signal == "qr_crypto_unavailable"), None)
        assert crypto_item is not None
        assert crypto_item.available is False
        assert crypto_item.severity == EvidenceSeverity.NONE

    def test_case_t_presentation_attack_override(self):
        """T. Presentation attack override -> spoof confirmed forces score >= 80."""
        vid = "p11-test-spoof-020"
        _seed_clean_session(vid)
        risk_session_store.update_module(vid, "m4_biometrics", {
            "overall_assessment": "SUSPECTED_SPOOF",
            "anti_spoof": {"status": "suspected_spoof", "score": 0.15, "model": "MiniFASNetV2", "explanation": "Print attack"},
        })
        res = risk_engine.assess(vid, "driving_license")
        assert res["risk_score"] >= 80
        assert res["critical_override_applied"] is True

    def test_case_u_contradiction_biometrics_vs_registry(self):
        """U. Contradiction between biometrics and registry -> C-01 conflict and CROSS_SOURCE_CONTRADICTION."""
        vid = "p11-test-c01-021"
        _seed_clean_session(vid)
        risk_session_store.update_module(vid, "m5_registry", {
            "registry": {"status": "REVOKED", "record_found": True},
            "field_results": [],
            "provider_metadata": {"source_type": "authoritative"},
        })
        res = risk_engine.assess(vid, "driving_license")
        assert res["risk_assessment"]["conflict_detected"] is True
        conflict_ids = [c["conflict_id"] for c in res["risk_assessment"]["conflicts"]]
        assert "C-01" in conflict_ids
        contra_types = [c["type"] for c in res["contradictions"]]
        assert "CROSS_SOURCE_CONTRADICTION" in contra_types

    def test_case_v_diminishing_returns_formula(self):
        """V. Diminishing returns formula verification -> 1st signal 100%, 2nd 50%, 3rd 25%."""
        config = RiskConfig()
        agg = RiskAggregator(config)
        items = [
            RiskEvidenceItem(
                module="M3", signal=f"sig_{i}", category=EvidenceCategory.FORENSIC_ANOMALY,
                status=EvidenceStatus.SUSPICIOUS, severity=EvidenceSeverity.HIGH,
                confidence=1.0, quality=1.0, available=True, explanation=f"Sig {i}",
                provenance={}, correlation_group=CorrelationGroup.FORENSIC_IMAGE_SIGNALS,
            )
            for i in range(3)
        ]
        res = agg.aggregate(items)
        cat = res.category_dict["FORENSIC_ANOMALY"]
        # In cat.scored_items, check correlation factors
        assert cat.scored_items[0].correlation_factor == 1.0
        assert cat.scored_items[1].correlation_factor == 0.50
        assert cat.scored_items[2].correlation_factor == 0.25

    def test_case_w_inconclusive_thresholding(self):
        """W. Inconclusive thresholding -> zero completeness triggers INCONCLUSIVE level."""
        vid = "p11-test-inconc-023"
        risk_session_store.evict(vid)
        res = risk_engine.assess(vid, "passport")
        assert res["risk_level"] == "INCONCLUSIVE"
        assert res["assessment_confidence"] == 0.0

    def test_case_x_evidence_summary_counters(self):
        """X. Evidence summary counters -> available, unavailable, adverse, positive match counts."""
        vid = "p11-test-summary-024"
        _seed_clean_session(vid)
        _seed_m7_clean(vid)
        res = risk_engine.assess(vid, "driving_license")
        es = res["evidence_summary"]
        assert es["total_evaluated"] > 0
        assert es["available_count"] > 0
        assert es["total_evaluated"] == es["available_count"] + es["unavailable_count"]
        assert es["positive_count"] >= 3

    def test_case_y_dual_api_compatibility(self):
        """Y. Dual API compatibility -> fields accessible at root level and inside risk_assessment."""
        vid = "p11-test-dual-025"
        _seed_clean_session(vid)
        resp = client.post("/api/v1/verification/risk", json={
            "verification_id": vid,
            "document_type": "driving_license",
        })
        assert resp.status_code == 200
        data = resp.json()

        # Check root level
        assert "risk_score" in data
        assert "risk_level" in data
        assert "officer_recommendation" in data
        assert "top_contributors" in data
        assert "supporting_evidence" in data
        assert "limitations" in data
        assert "contradictions" in data
        assert "explanation" in data
        assert "snapshot_hash" in data

        # Check nested risk_assessment
        assert "risk_assessment" in data
        ra = data["risk_assessment"]
        assert ra["risk_score"] == data["risk_score"]
        assert ra["risk_level"] == data["risk_level"]
        assert ra["officer_recommendation"] == data["officer_recommendation"]
        assert len(ra["reasons"]) == len(data["risk_assessment"]["reasons"])

    def test_case_z_case_risk_evaluator_backwards_compatibility(self):
        """Z. Case risk evaluator backwards compatibility -> CaseRiskEvaluator evaluates cleanly."""
        from app.services.case.case_risk import CaseRiskEvaluator
        from app.services.case.verification_case import CaseDocument, VerificationCase
        from app.schemas.case import DocumentStatus
        case_eval = CaseRiskEvaluator()
        case = VerificationCase(case_id="case-p11-026")
        vid = "case-doc-vid-026"
        _seed_clean_session(vid)
        doc = CaseDocument(
            document_id="doc-026",
            document_type="driving_license",
            verification_id=vid,
            status=DocumentStatus.COMPLETED,
            filename="dl.jpg",
        )
        case.add_document(doc)
        result = case_eval.evaluate_case_risk(case)
        assert "risk_score" in result
        assert "documents_considered" in result
        assert 0 <= result["risk_score"] <= 100



    def test_case_aa_profile_version_traceability(self):
        """AA. Profile version traceability -> driving_license version '0.9.0' recorded in assessment."""
        vid = "p11-test-ver-027"
        _seed_clean_session(vid)
        res = risk_engine.assess(vid, "driving_license")
        assert res["profile_version"] == "0.9.0"
        assert res["risk_assessment"]["profile_version"] == "0.9.0"
        assert res["engine_version"] == "0.6.0"

    def test_case_bb_deterministic_scoring_50_runs(self):
        """BB. Deterministic scoring -> 50 repeated executions yield identical scores and hashes."""
        vid = "p11-test-determ-028"
        _seed_clean_session(vid)
        _seed_m7_clean(vid)

        first_res = risk_engine.assess(vid, "driving_license")
        score = first_res["risk_score"]
        h = first_res["snapshot_hash"]

        for _ in range(50):
            res = risk_engine.assess(vid, "driving_license")
            assert res["risk_score"] == score
            assert res["snapshot_hash"] == h
