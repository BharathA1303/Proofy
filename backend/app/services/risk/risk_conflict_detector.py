"""
backend/app/services/risk/risk_conflict_detector.py

Conflict detection: identifies contradictory evidence patterns that
require explicit officer attention.

A conflict occurs when two or more independent modules produce findings
that are in tension with each other — not simply when one module fails.

Examples:
  - Document passes M2 validation AND biometrics pass (M4), BUT
    M3 forensics shows HIGH_FORENSIC_CONCERN → structural vs image evidence conflict.
  - Biometrics pass (M4 face match) BUT M5 registry returns REVOKED →
    the person presented matches the document face, but the document itself
    is revoked. The biometric result does NOT override the registry status.
  - M2 checks pass (internally consistent document), BUT M5 returns a
    document number MISMATCH → provenance inconsistency.

Design:
  - Pure function: no I/O, no randomness.
  - Returns a structured report; does NOT modify evidence items.
  - Conflicts do NOT directly add to the risk score — they are surfaced
    separately in the officer report so the reasoning is explicit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services.risk.risk_evidence import EvidenceStatus, RiskEvidenceItem


@dataclass
class ConflictItem:
    """A single detected conflict between evidence sources."""
    conflict_id: str
    description: str
    modules_involved: List[str]
    severity: str  # "warning" | "high"


@dataclass
class ConflictReport:
    """Result of the conflict detection pass."""
    detected: bool
    conflicts: List[ConflictItem] = field(default_factory=list)


def _has_status(items: List[RiskEvidenceItem], *statuses: str) -> bool:
    return any(i.status.value in statuses for i in items if i.available)


def _has_signal(items: List[RiskEvidenceItem], *signals: str) -> bool:
    return any(i.signal in signals for i in items if i.available)


def _get_m_items(items: List[RiskEvidenceItem], module: str) -> List[RiskEvidenceItem]:
    return [i for i in items if i.module == module]


class ConflictDetector:
    """
    Detects contradictory evidence patterns in the normalized evidence list.

    Each pattern is checked independently. Multiple conflicts can be active
    simultaneously.
    """

    def detect(self, items: List[RiskEvidenceItem]) -> ConflictReport:
        """
        Scan the full evidence list for conflict patterns.

        Args:
            items: All normalized evidence items from M1–M5.

        Returns:
            ConflictReport with detected flag and list of ConflictItems.
        """
        conflicts: List[ConflictItem] = []

        m2 = _get_m_items(items, "M2")
        m3 = _get_m_items(items, "M3")
        m4 = _get_m_items(items, "M4")
        m5 = _get_m_items(items, "M5")

        # ── C-01: Biometrics pass but registry revoked/suspended ────────────
        biometric_pass = _has_signal(m4, "face_match_pass") or (
            not _has_signal(m4, "face_mismatch_high_quality",
                            "face_mismatch_poor_quality", "presentation_attack_detected")
            and len([i for i in m4 if i.available]) > 0
        )
        registry_adverse = _has_status(m5, "REVOKED", "SUSPENDED", "MISMATCH")

        if biometric_pass and registry_adverse:
            reg_status = next(
                (i.status.value for i in m5 if i.status.value in ("REVOKED", "SUSPENDED", "MISMATCH")),
                "adverse status"
            )
            conflicts.append(ConflictItem(
                conflict_id="C-01",
                description=(
                    f"Biometric verification indicates the presented person corresponds to "
                    f"the document photograph, but the registry returns '{reg_status}'. "
                    f"A positive biometric result does not override an adverse registry status. "
                    f"The document itself requires scrutiny."
                ),
                modules_involved=["M4", "M5"],
                severity="high",
            ))

        # ── C-02: Document internally consistent but high forensic concern ──
        m2_consistent = not _has_signal(m2,
            "document_number_binding_mismatch",
            "viz_mrz_document_number_mismatch",
            "document_number_checksum_fail",
        )
        m3_high_concern = _has_signal(m3, "forensic_high_concern")

        if m2_consistent and m3_high_concern and len([i for i in m2 if i.available]) > 0:
            conflicts.append(ConflictItem(
                conflict_id="C-02",
                description=(
                    "Document data fields are internally consistent (M2 validation passed), "
                    "but image-level forensic analysis indicates significant anomalies (M3). "
                    "Structural integrity and image integrity are independent properties. "
                    "Both require officer review."
                ),
                modules_involved=["M2", "M3"],
                severity="warning",
            ))

        # ── C-03: M2 validation pass but M5 registry document-number mismatch
        m2_passed = not any(
            i.signal in ("document_number_checksum_fail", "document_number_binding_mismatch",
                         "viz_mrz_document_number_mismatch")
            for i in m2 if i.available
        )
        m5_doc_mismatch = _has_signal(m5, "registry_field_mismatch", "registry_mismatch")

        if m2_passed and m5_doc_mismatch and len([i for i in m5 if i.available]) > 0:
            conflicts.append(ConflictItem(
                conflict_id="C-03",
                description=(
                    "Document number fields are internally consistent (M2), but the "
                    "registry returns a field mismatch (M5). The document may have been "
                    "issued with a different number than the one presented, or the registry "
                    "record may refer to a different document."
                ),
                modules_involved=["M2", "M5"],
                severity="warning",
            ))

        # ── C-04: Presentation attack suspected but registry matched ─────────
        pad_flag = _has_signal(m4, "presentation_attack_detected")
        # registry_matched items use EvidenceStatus.PASS (positive evidence generates no adverse item)
        # Check for the absence of any adverse M5 status as a proxy for "registry matched"
        registry_matched = (
            _has_status(m5, "MATCHED") or
            _has_signal(m5, "registry_matched") or
            (len(m5) > 0 and not any(
                i.status.value in ("REVOKED", "SUSPENDED", "MISMATCH", "NOT_FOUND",
                                   "EXPIRED", "INVALID", "AMBIGUOUS", "INCONCLUSIVE")
                for i in m5 if i.available
            ) and len([i for i in m5 if i.available]) > 0)
        )

        if pad_flag and registry_matched:
            conflicts.append(ConflictItem(
                conflict_id="C-04",
                description=(
                    "Presentation attack suspected (M4): the live capture may not be "
                    "a genuine biometric. The registry confirms the document exists (M5). "
                    "Registry matching does not address liveness — this combination "
                    "warrants heightened officer scrutiny of the live subject."
                ),
                modules_involved=["M4", "M5"],
                severity="high",
            ))

        # ── C-05: Multiple independent adverse signals (M2 + M3 + M5) ──────
        m2_adverse = any(i.available for i in m2
                         if i.signal in ("document_number_checksum_fail",
                                         "document_number_binding_mismatch"))
        m3_suspicious = _has_signal(m3, "forensic_high_concern", "forensic_suspicious")
        m5_adverse_status = _has_status(m5, "REVOKED", "MISMATCH", "SUSPENDED", "NOT_FOUND")

        if sum([m2_adverse, m3_suspicious, m5_adverse_status]) >= 2:
            modules = ([" M2"] if m2_adverse else []) + (["M3"] if m3_suspicious else []) + (["M5"] if m5_adverse_status else [])
            conflicts.append(ConflictItem(
                conflict_id="C-05",
                description=(
                    "Multiple independent verification modules produced adverse findings: "
                    + ", ".join(m.strip() for m in modules) + ". "
                    "Independent adverse signals across separate evidence sources "
                    "require thorough officer review."
                ),
                modules_involved=[m.strip() for m in modules],
                severity="high",
            ))

        return ConflictReport(
            detected=len(conflicts) > 0,
            conflicts=conflicts,
        )
