"""
tests/test_risk_rules.py

Unit tests for the risk rule table.
Verifies every signal × severity cell returns expected contribution.
"""
from __future__ import annotations

import pytest
from app.services.risk.risk_rules import get_base_contribution, RULE_TABLE
from app.services.risk.risk_evidence import (
    EvidenceCategory, EvidenceSeverity, EvidenceStatus, RiskEvidenceItem
)


def _item(signal, severity, status=EvidenceStatus.FAIL, available=True):
    return RiskEvidenceItem(
        module="M2",
        signal=signal,
        category=EvidenceCategory.DOCUMENT_INTEGRITY,
        status=status,
        severity=severity,
        confidence=0.95,
        available=available,
        explanation="Test.",
        provenance={},
    )


def test_none_severity_always_zero():
    for signal in RULE_TABLE:
        item = _item(signal, EvidenceSeverity.NONE, status=EvidenceStatus.PASS)
        assert get_base_contribution(item) == 0.0


def test_unavailable_items_always_zero():
    """Unavailable items are handled by uncertainty, not the rule table."""
    item = _item("registry_revoked", EvidenceSeverity.CRITICAL, available=False)
    assert get_base_contribution(item) == 0.0


def test_revoked_critical_highest():
    item = _item("registry_revoked", EvidenceSeverity.CRITICAL, status=EvidenceStatus.REVOKED)
    item.category = EvidenceCategory.REGISTRY_STATUS
    assert get_base_contribution(item) == 22.0


def test_presentation_attack_critical():
    item = _item("presentation_attack_detected", EvidenceSeverity.CRITICAL, status=EvidenceStatus.SUSPICIOUS)
    assert get_base_contribution(item) == 20.0


def test_face_mismatch_high_quality_high():
    item = _item("face_mismatch_high_quality", EvidenceSeverity.HIGH, status=EvidenceStatus.MISMATCH)
    assert get_base_contribution(item) == 17.0


def test_face_mismatch_poor_quality_lower():
    poor = _item("face_mismatch_poor_quality", EvidenceSeverity.HIGH, status=EvidenceStatus.MISMATCH)
    good = _item("face_mismatch_high_quality", EvidenceSeverity.HIGH, status=EvidenceStatus.MISMATCH)
    assert get_base_contribution(poor) < get_base_contribution(good)


def test_doc_number_binding_critical():
    item = _item("document_number_binding_mismatch", EvidenceSeverity.CRITICAL, status=EvidenceStatus.MISMATCH)
    assert get_base_contribution(item) == 20.0


def test_checksum_fail_high():
    item = _item("document_number_checksum_fail", EvidenceSeverity.HIGH)
    assert get_base_contribution(item) == 14.0


def test_unknown_signal_uses_fallback():
    item = _item("nonexistent_signal_xyz", EvidenceSeverity.HIGH)
    contribution = get_base_contribution(item)
    assert contribution == 7.0  # fallback HIGH


def test_registry_matched_zero():
    item = _item("registry_matched", EvidenceSeverity.NONE, status=EvidenceStatus.PASS)
    assert get_base_contribution(item) == 0.0


def test_registry_not_found_medium():
    item = _item("registry_not_found", EvidenceSeverity.MEDIUM, status=EvidenceStatus.NOT_FOUND)
    assert get_base_contribution(item) == 6.0


def test_registry_not_found_high():
    item = _item("registry_not_found", EvidenceSeverity.HIGH, status=EvidenceStatus.NOT_FOUND)
    assert get_base_contribution(item) == 10.0


def test_all_rule_table_keys_have_none_entry():
    """Every signal must have a NONE severity entry to handle positive evidence."""
    for signal, severity_map in RULE_TABLE.items():
        assert "NONE" in severity_map, f"Signal '{signal}' missing NONE entry"
        assert severity_map["NONE"] == 0.0, f"Signal '{signal}' NONE entry must be 0.0"
