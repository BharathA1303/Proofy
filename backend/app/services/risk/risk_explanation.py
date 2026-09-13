"""
backend/app/services/risk/risk_explanation.py

Human-readable reason generation for the officer decision support panel.

Design:
  - Every reason references a specific evidence item (module, signal, source).
  - No vague "AI detected risk" explanations.
  - Reasons generated only for severity ≥ LOW (NONE → no reason generated).
  - Reasons sorted by effective contribution (highest first).
  - Uncertain items are surfaced separately as uncertainties.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from app.services.risk.risk_aggregator import AggregationResult, ScoredItem
from app.services.risk.risk_evidence import EvidenceSeverity, EvidenceStatus, RiskEvidenceItem


@dataclass
class RiskReason:
    """A single officer-facing reason with full provenance."""
    reason_id: str
    module: str
    signal: str
    severity: str
    confidence: float
    contribution: float
    explanation: str
    provenance: dict


@dataclass
class UncertaintyItem:
    """An evidence item that is operationally significant but low-confidence."""
    module: str
    signal: str
    explanation: str
    confidence: float
    severity: str


class ExplanationBuilder:
    """Generates human-readable officer reasons from scored evidence."""

    def build_reasons(
        self, aggregation: AggregationResult
    ) -> tuple[List[RiskReason], List[UncertaintyItem]]:
        """
        Build officer-facing reasons and uncertainty items.

        Returns:
            reasons: Sorted list of adverse evidence reasons (highest contribution first).
            uncertainties: High-severity but low-confidence items flagged for officer attention.
        """
        reasons: List[RiskReason] = []
        uncertainties: List[UncertaintyItem] = []
        reason_counter = 0

        all_scored: List[ScoredItem] = []
        for cat_result in aggregation.category_results:
            all_scored.extend(cat_result.scored_items)

        # Sort by effective contribution descending
        all_scored.sort(key=lambda s: s.effective_contribution, reverse=True)

        for scored in all_scored:
            item = scored.item
            if item.severity == EvidenceSeverity.NONE:
                continue  # No reason for positive/neutral evidence

            if item.is_uncertain:
                uncertainties.append(UncertaintyItem(
                    module=item.module,
                    signal=item.signal,
                    explanation=item.explanation,
                    confidence=item.confidence,
                    severity=item.severity.value,
                ))

            if scored.effective_contribution > 0.0:
                reason_counter += 1
                reasons.append(RiskReason(
                    reason_id=f"R-{item.module}-{reason_counter:03d}",
                    module=item.module,
                    signal=item.signal,
                    severity=item.severity.value,
                    confidence=round(item.confidence, 3),
                    contribution=round(scored.effective_contribution, 2),
                    explanation=item.explanation,
                    provenance=item.provenance,
                ))

        return reasons, uncertainties

    def build_top_contributors(
        self, aggregation: AggregationResult
    ) -> List[Dict[str, Any]]:
        """
        Ranked adverse evidence contributors ordered by score contribution descending.
        """
        all_scored: List[ScoredItem] = []
        for cat_result in aggregation.category_results:
            all_scored.extend(cat_result.scored_items)

        # Filter to items that contributed adverse risk
        adverse_scored = [s for s in all_scored if s.effective_contribution > 0.0]
        adverse_scored.sort(key=lambda s: s.effective_contribution, reverse=True)

        top: List[Dict[str, Any]] = []
        for scored in adverse_scored[:5]:
            item = scored.item
            top.append({
                "source_module": item.source_module or item.module,
                "evidence_type": item.evidence_type or item.signal,
                "contribution": round(scored.effective_contribution, 2),
                "raw_value": item.value or item.provenance.get("value") or item.provenance.get("signal_status"),
                "reliability": round(item.reliability, 3),
                "explanation": item.explanation,
            })
        return top

    def build_supporting_evidence(
        self, items: List[RiskEvidenceItem]
    ) -> List[Dict[str, Any]]:
        """
        Extract positive corroborating findings supporting consistency or validity.
        """
        supporting: List[Dict[str, Any]] = []
        seen_signals = set()

        for item in items:
            if not item.available:
                continue
            if item.is_positive or item.severity == EvidenceSeverity.NONE:
                if item.signal in seen_signals:
                    continue
                seen_signals.add(item.signal)
                st = "CORROBORATED" if item.status == EvidenceStatus.MATCH else "PASS"
                supporting.append({
                    "source_module": item.source_module or item.module,
                    "evidence_type": item.evidence_type or item.signal,
                    "status": st,
                    "explanation": item.explanation,
                })
        return supporting

    def build_limitations(
        self, items: List[RiskEvidenceItem]
    ) -> List[Dict[str, Any]]:
        """
        Extract unrun, unconfigured, or inconclusive module signals.
        """
        limitations: List[Dict[str, Any]] = []
        seen = set()

        for item in items:
            if not item.available or item.status in (EvidenceStatus.UNAVAILABLE, EvidenceStatus.NOT_RUN, EvidenceStatus.INCONCLUSIVE):
                key = (item.module, item.signal)
                if key in seen:
                    continue
                seen.add(key)
                impact = "HIGH" if item.module in ("M1", "M2") else ("MEDIUM" if item.module in ("M4", "M5") else "LOW")
                limitations.append({
                    "source_module": item.source_module or item.module,
                    "limitation": item.explanation,
                    "impact": impact,
                })
        return limitations

    def build_explanation_text(
        self,
        risk_score: int,
        risk_level: str,
        officer_recommendation: str,
        top_contributors: List[Dict[str, Any]],
        supporting_evidence: List[Dict[str, Any]],
        limitations: List[Dict[str, Any]],
        contradictions: List[Dict[str, Any]],
        critical_override: bool = False,
    ) -> str:
        """
        Generate a deterministic multi-paragraph officer summary without hallucinations.
        """
        # Paragraph 1: Executive scoring and advisory status
        override_note = " (triggered by critical policy override)" if critical_override else ""
        p1 = (
            f"Assessment Summary: Deterministic risk score is {risk_score}/100 "
            f"({risk_level} risk level{override_note}). "
            f"Advisory guidance: {officer_recommendation}. "
            f"This scoring is a decision-support indicator and does not represent an automated screening decision."
        )

        # Paragraph 2: Adverse findings and contradictions
        if contradictions:
            contra_desc = "; ".join(c.get("explanation", "") for c in contradictions[:2])
            contra_text = f" Critical cross-source discrepancy observed: {contra_desc}."
        else:
            contra_text = ""

        if top_contributors:
            contrib_text = "; ".join(f"{c['source_module']}: {c['explanation']}" for c in top_contributors[:3])
            p2 = f"Primary Risk Contributors: {contrib_text}.{contra_text}"
        elif contradictions:
            p2 = f"Cross-Source Consistency: No individual module score spikes, but{contra_text.lower()}"
        else:
            p2 = "Primary Risk Contributors: No significant tampering, biometric mismatch, or structural anomalies detected."

        # Paragraph 3: Corroboration & Limitations
        corrob_text = (
            f"Positive corroboration confirmed across {len(supporting_evidence)} verified checks. "
            if supporting_evidence else "Positive corroboration is limited. "
        )
        if limitations:
            lim_text = f"Operational limitations noted in {len(limitations)} area(s), including: {limitations[0]['limitation']}"
        else:
            lim_text = "All configured screening modules completed with full data availability."
        p3 = f"Corroboration and Scope: {corrob_text}{lim_text}"

        return f"{p1}\n\n{p2}\n\n{p3}"

