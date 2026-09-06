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
from typing import List

from app.services.risk.risk_aggregator import AggregationResult, ScoredItem
from app.services.risk.risk_evidence import EvidenceSeverity, RiskEvidenceItem


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
