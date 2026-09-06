"""
tests/test_risk_aggregator.py

Unit tests for the risk aggregator.
Verifies: category caps, correlation protection, confidence adjustment,
bounded output, determinism.
"""
from __future__ import annotations

import pytest
from app.services.risk.risk_aggregator import RiskAggregator
from app.services.risk.risk_config import RiskConfig
from app.services.risk.risk_evidence import (
    CorrelationGroup, EvidenceCategory, EvidenceSeverity, EvidenceStatus, RiskEvidenceItem
)


def _config():
    return RiskConfig()


def _item(signal, severity, category, confidence=0.95, available=True, cg=None):
    return RiskEvidenceItem(
        module="M3",
        signal=signal,
        category=category,
        status=EvidenceStatus.FAIL if severity != EvidenceSeverity.NONE else EvidenceStatus.PASS,
        severity=severity,
        confidence=confidence,
        available=available,
        explanation="Test.",
        provenance={},
        correlation_group=cg,
    )


def test_empty_evidence_returns_zero():
    agg = RiskAggregator(_config())
    result = agg.aggregate([])
    assert result.risk_score == 0


def test_positive_only_returns_zero():
    items = [
        _item("registry_matched", EvidenceSeverity.NONE, EvidenceCategory.REGISTRY_STATUS),
        _item("face_match_pass", EvidenceSeverity.NONE, EvidenceCategory.BIOMETRIC_CONSISTENCY),
    ]
    agg = RiskAggregator(_config())
    result = agg.aggregate(items)
    assert result.risk_score == 0


def test_single_critical_item_contributes():
    items = [_item("registry_revoked", EvidenceSeverity.CRITICAL, EvidenceCategory.REGISTRY_STATUS)]
    agg = RiskAggregator(_config())
    result = agg.aggregate(items)
    assert result.risk_score > 0
    reg_result = result.category_dict.get("REGISTRY_STATUS")
    assert reg_result is not None
    assert reg_result.contribution > 0


def test_category_cap_respected():
    """Many high-severity items in one category must not exceed the cap."""
    config = _config()
    cap = config.cap_for(EvidenceCategory.DOCUMENT_INTEGRITY)
    items = [
        _item("document_number_checksum_fail", EvidenceSeverity.HIGH, EvidenceCategory.DOCUMENT_INTEGRITY)
        for _ in range(10)
    ]
    agg = RiskAggregator(config)
    result = agg.aggregate(items)
    doc_int = result.category_dict.get("DOCUMENT_INTEGRITY")
    assert doc_int.contribution <= cap + 0.001  # floating point tolerance


def test_total_score_bounded_at_100():
    """Even with all adverse signals, score must not exceed 100."""
    items = [
        _item("registry_revoked", EvidenceSeverity.CRITICAL, EvidenceCategory.REGISTRY_STATUS),
        _item("presentation_attack_detected", EvidenceSeverity.CRITICAL, EvidenceCategory.PRESENTATION_ATTACK),
        _item("face_mismatch_high_quality", EvidenceSeverity.HIGH, EvidenceCategory.BIOMETRIC_CONSISTENCY),
        _item("forensic_high_concern", EvidenceSeverity.HIGH, EvidenceCategory.FORENSIC_ANOMALY),
        _item("document_number_binding_mismatch", EvidenceSeverity.CRITICAL, EvidenceCategory.DOCUMENT_CONSISTENCY),
        _item("document_number_checksum_fail", EvidenceSeverity.HIGH, EvidenceCategory.DOCUMENT_INTEGRITY),
        _item("dob_checksum_fail", EvidenceSeverity.HIGH, EvidenceCategory.DOCUMENT_INTEGRITY),
        _item("mrz_unavailable", EvidenceSeverity.HIGH, EvidenceCategory.DOCUMENT_STRUCTURE),
    ]
    agg = RiskAggregator(_config())
    result = agg.aggregate(items)
    assert result.risk_score <= 100


def test_correlation_protection():
    """Correlated signals should have diminishing returns."""
    config = _config()
    # Two ELA + compression in same group
    items_correlated = [
        _item("forensic_ela_anomaly", EvidenceSeverity.HIGH, EvidenceCategory.FORENSIC_ANOMALY,
              cg=CorrelationGroup.FORENSIC_IMAGE_SIGNALS),
        _item("forensic_compression_anomaly", EvidenceSeverity.MEDIUM, EvidenceCategory.FORENSIC_ANOMALY,
              cg=CorrelationGroup.FORENSIC_IMAGE_SIGNALS),
    ]
    # Same two signals without correlation
    items_uncorrelated = [
        _item("forensic_ela_anomaly", EvidenceSeverity.HIGH, EvidenceCategory.FORENSIC_ANOMALY),
        _item("forensic_compression_anomaly", EvidenceSeverity.MEDIUM, EvidenceCategory.FORENSIC_ANOMALY),
    ]

    agg = RiskAggregator(config)
    r_corr = agg.aggregate(items_correlated)
    r_uncorr = agg.aggregate(items_uncorrelated)

    # Correlated should contribute less than uncorrelated
    assert r_corr.risk_score < r_uncorr.risk_score


def test_confidence_adjustment():
    """Low confidence items should contribute less than high-confidence items."""
    config = _config()

    high_conf = [_item("registry_revoked", EvidenceSeverity.CRITICAL, EvidenceCategory.REGISTRY_STATUS,
                       confidence=0.99)]
    low_conf = [_item("registry_revoked", EvidenceSeverity.CRITICAL, EvidenceCategory.REGISTRY_STATUS,
                      confidence=0.30)]

    agg = RiskAggregator(config)
    r_high = agg.aggregate(high_conf)
    r_low = agg.aggregate(low_conf)
    assert r_high.risk_score > r_low.risk_score


def test_unavailable_item_goes_to_uncertainty():
    items = [
        _item("module_not_run", EvidenceSeverity.LOW, EvidenceCategory.VERIFICATION_UNCERTAINTY,
              available=False)
    ]
    agg = RiskAggregator(_config())
    result = agg.aggregate(items)
    # Should still have a small score from uncertainty
    uncert = result.category_dict.get("VERIFICATION_UNCERTAINTY")
    assert uncert is not None


def test_determinism():
    """Same input → identical output every time."""
    config = _config()
    items = [
        _item("registry_revoked", EvidenceSeverity.CRITICAL, EvidenceCategory.REGISTRY_STATUS),
        _item("face_mismatch_high_quality", EvidenceSeverity.HIGH, EvidenceCategory.BIOMETRIC_CONSISTENCY),
        _item("forensic_ela_anomaly", EvidenceSeverity.HIGH, EvidenceCategory.FORENSIC_ANOMALY,
              cg=CorrelationGroup.FORENSIC_IMAGE_SIGNALS),
    ]
    agg = RiskAggregator(config)
    scores = [agg.aggregate(items).risk_score for _ in range(10)]
    assert len(set(scores)) == 1, f"Non-deterministic: {scores}"
