"""
tests/test_risk_conflict_detector.py

Unit tests for the conflict detection patterns (C-01 through C-05).
"""
from __future__ import annotations

import pytest
from app.services.risk.risk_conflict_detector import ConflictDetector
from app.services.risk.risk_evidence import (
    EvidenceCategory, EvidenceSeverity, EvidenceStatus, RiskEvidenceItem
)


def _item(module, signal, status, category=EvidenceCategory.REGISTRY_STATUS,
          severity=EvidenceSeverity.HIGH, available=True):
    return RiskEvidenceItem(
        module=module, signal=signal, category=category,
        status=status, severity=severity, confidence=0.95,
        available=available, explanation="Test.", provenance={},
    )


def _m4_positive():
    """M4 items with no adverse biometric signals (positive match scenario)."""
    return [RiskEvidenceItem(
        module="M4", signal="face_match_pass",
        category=EvidenceCategory.BIOMETRIC_CONSISTENCY,
        status=EvidenceStatus.PASS, severity=EvidenceSeverity.NONE,
        confidence=0.95, available=True, explanation="Match.", provenance={},
    )]


def _m5_matched():
    """M5 item with registry_matched (positive evidence — PASS status)."""
    return RiskEvidenceItem(
        module="M5", signal="registry_matched",
        category=EvidenceCategory.REGISTRY_STATUS,
        status=EvidenceStatus.PASS, severity=EvidenceSeverity.NONE,
        confidence=1.0, available=True, explanation="Matched.", provenance={},
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_no_conflicts_clean():
    """Clean session: no conflicts."""
    items = [
        RiskEvidenceItem(
            module="M5", signal="registry_matched", category=EvidenceCategory.REGISTRY_STATUS,
            status=EvidenceStatus.PASS, severity=EvidenceSeverity.NONE,
            confidence=1.0, available=True, explanation="Matched.", provenance={},
        ),
    ]
    detector = ConflictDetector()
    report = detector.detect(items)
    assert not report.detected
    assert len(report.conflicts) == 0


def test_c01_biometrics_pass_registry_revoked():
    """C-01: Face match passes but registry revoked."""
    items = _m4_positive() + [
        _item("M5", "registry_revoked", EvidenceStatus.REVOKED,
              category=EvidenceCategory.REGISTRY_STATUS, severity=EvidenceSeverity.CRITICAL),
    ]
    detector = ConflictDetector()
    report = detector.detect(items)
    assert report.detected
    ids = [c.conflict_id for c in report.conflicts]
    assert "C-01" in ids


def test_c02_m2_consistent_m3_high_concern():
    """C-02: M2 consistent (positive item) + M3 high forensic concern."""
    # A positive M2 item (module ran but found no adverse signal)
    m2_positive = RiskEvidenceItem(
        module="M2", signal="mrz_structure_passed",
        category=EvidenceCategory.DOCUMENT_STRUCTURE,
        status=EvidenceStatus.PASS, severity=EvidenceSeverity.NONE,
        confidence=0.95, available=True, explanation="MRZ OK.", provenance={},
    )
    items = [
        m2_positive,
        _item("M3", "forensic_high_concern", EvidenceStatus.SUSPICIOUS,
              category=EvidenceCategory.FORENSIC_ANOMALY, severity=EvidenceSeverity.HIGH),
    ]
    detector = ConflictDetector()
    report = detector.detect(items)
    assert report.detected
    ids = [c.conflict_id for c in report.conflicts]
    assert "C-02" in ids


def test_c04_pad_suspected_registry_matched():
    """C-04: PAD suspected + registry confirms document (no adverse M5 signals)."""
    items = [
        _item("M4", "presentation_attack_detected", EvidenceStatus.SUSPICIOUS,
              category=EvidenceCategory.PRESENTATION_ATTACK, severity=EvidenceSeverity.CRITICAL),
        _m5_matched(),
    ]
    detector = ConflictDetector()
    report = detector.detect(items)
    # C-04: PAD flag + registry registry_matched signal → conflict
    assert report.detected
    ids = [c.conflict_id for c in report.conflicts]
    assert "C-04" in ids


def test_multiple_conflicts_detected():
    """Multiple independent adverse signals trigger multiple conflicts."""
    items = _m4_positive() + [
        _item("M5", "registry_revoked", EvidenceStatus.REVOKED,
              category=EvidenceCategory.REGISTRY_STATUS, severity=EvidenceSeverity.CRITICAL),
        _item("M3", "forensic_high_concern", EvidenceStatus.SUSPICIOUS,
              category=EvidenceCategory.FORENSIC_ANOMALY, severity=EvidenceSeverity.HIGH),
        _item("M2", "document_number_checksum_fail", EvidenceStatus.FAIL,
              category=EvidenceCategory.DOCUMENT_INTEGRITY, severity=EvidenceSeverity.HIGH),
    ]
    detector = ConflictDetector()
    report = detector.detect(items)
    assert report.detected
    # Should find at least C-01 (biometrics+revoked) and C-05 (multiple adverse)
    assert len(report.conflicts) >= 2


def test_conflict_ids_unique():
    """All detected conflict IDs must be unique."""
    items = _m4_positive() + [
        _item("M5", "registry_revoked", EvidenceStatus.REVOKED,
              category=EvidenceCategory.REGISTRY_STATUS, severity=EvidenceSeverity.CRITICAL),
    ]
    detector = ConflictDetector()
    report = detector.detect(items)
    ids = [c.conflict_id for c in report.conflicts]
    assert len(ids) == len(set(ids))


def test_conflict_modules_listed():
    """Conflict report must list modules involved."""
    items = _m4_positive() + [
        _item("M5", "registry_revoked", EvidenceStatus.REVOKED,
              category=EvidenceCategory.REGISTRY_STATUS, severity=EvidenceSeverity.CRITICAL),
    ]
    detector = ConflictDetector()
    report = detector.detect(items)
    c01 = next(c for c in report.conflicts if c.conflict_id == "C-01")
    assert len(c01.modules_involved) >= 1


def test_empty_evidence_no_conflicts():
    """Empty evidence must never trigger a conflict."""
    detector = ConflictDetector()
    report = detector.detect([])
    assert not report.detected


def test_c05_multiple_adverse_modules():
    """C-05: Two or more of M2-adverse + M3-suspicious + M5-adverse."""
    items = [
        _item("M2", "document_number_checksum_fail", EvidenceStatus.FAIL,
              category=EvidenceCategory.DOCUMENT_INTEGRITY, severity=EvidenceSeverity.HIGH),
        _item("M3", "forensic_high_concern", EvidenceStatus.SUSPICIOUS,
              category=EvidenceCategory.FORENSIC_ANOMALY, severity=EvidenceSeverity.HIGH),
        _item("M5", "registry_not_found", EvidenceStatus.NOT_FOUND,
              category=EvidenceCategory.REGISTRY_STATUS, severity=EvidenceSeverity.MEDIUM),
    ]
    detector = ConflictDetector()
    report = detector.detect(items)
    assert report.detected
    ids = [c.conflict_id for c in report.conflicts]
    assert "C-05" in ids
