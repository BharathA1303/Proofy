"""
backend/app/services/risk/risk_aggregator.py

Risk score aggregator: groups evidence by category, applies correlation
protection, confidence adjustments, and category caps.

Design:
  - Pure function: no I/O, no state, no randomness.
  - Deterministic: same input → identical output always.
  - Implements the three-tier protection:
    1. Correlation group diminishing returns (prevents double-counting)
    2. Confidence adjustment (low-confidence signals have less influence)
    3. Category cap (prevents single-category score explosion)
  - Final score: min(sum(category_contributions), 100)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from app.services.risk.risk_config import RiskConfig
from app.services.risk.risk_evidence import (
    CorrelationGroup,
    EvidenceCategory,
    EvidenceSeverity,
    RiskEvidenceItem,
)
from app.services.risk.risk_rules import get_base_contribution


@dataclass
class ScoredItem:
    """An evidence item after rule evaluation and confidence adjustment."""
    item: RiskEvidenceItem
    base_contribution: float
    confidence_factor: float
    correlation_factor: float  # 1.0 for primary; secondary_factor for correlated peers
    effective_contribution: float


@dataclass
class CategoryResult:
    """Score result for a single evidence category."""
    category: EvidenceCategory
    category_label: str
    raw_contribution: float   # before cap
    contribution: float       # after cap (min(raw, cap))
    maximum: float            # the cap value
    scored_items: List[ScoredItem] = field(default_factory=list)


@dataclass
class AggregationResult:
    """Final aggregation result."""
    risk_score: int
    category_results: List[CategoryResult]

    @property
    def category_dict(self) -> Dict[str, CategoryResult]:
        return {r.category.value: r for r in self.category_results}


class RiskAggregator:
    """
    Aggregates RiskEvidenceItems into a final risk score 0–100.

    Flow per category:
      1. Collect items for this category.
      2. Compute base contribution via rule table.
      3. Apply correlation protection within correlation groups.
      4. Apply confidence adjustment.
      5. Sum, cap at category maximum.

    Final score = min(sum of all category contributions, 100).
    """

    def __init__(self, config: RiskConfig) -> None:
        self._config = config

    def aggregate(self, items: List[RiskEvidenceItem]) -> AggregationResult:
        # Separate available vs unavailable items
        # Unavailable items go to VERIFICATION_UNCERTAINTY with fixed small contribution
        available_items = [i for i in items if i.available]
        unavailable_items = [i for i in items if not i.available]

        category_results: List[CategoryResult] = []

        for category in EvidenceCategory:
            cat_items = [i for i in available_items if i.category == category]
            if not cat_items:
                category_results.append(CategoryResult(
                    category=category,
                    category_label=self._config.label_for(category),
                    raw_contribution=0.0,
                    contribution=0.0,
                    maximum=self._config.cap_for(category),
                ))
                continue

            scored = self._score_items(cat_items)
            raw = sum(s.effective_contribution for s in scored)
            cap = self._config.cap_for(category)
            capped = min(raw, cap)

            category_results.append(CategoryResult(
                category=category,
                category_label=self._config.label_for(category),
                raw_contribution=raw,
                contribution=capped,
                maximum=cap,
                scored_items=scored,
            ))

        # Uncertainty: sum unavailable items contributions separately
        uncert_cap = self._config.cap_for(EvidenceCategory.VERIFICATION_UNCERTAINTY)
        existing_uncert = next(
            (r for r in category_results
             if r.category == EvidenceCategory.VERIFICATION_UNCERTAINTY), None
        )

        if unavailable_items and existing_uncert is not None:
            uncert_scored = self._score_items(
                [i for i in unavailable_items
                 if i.category == EvidenceCategory.VERIFICATION_UNCERTAINTY]
                + [i for i in unavailable_items
                   if i.category != EvidenceCategory.VERIFICATION_UNCERTAINTY]
            )
            extra_uncert = sum(s.effective_contribution for s in uncert_scored)
            new_raw = existing_uncert.raw_contribution + extra_uncert
            existing_uncert.raw_contribution = new_raw
            existing_uncert.contribution = min(new_raw, uncert_cap)
            existing_uncert.scored_items.extend(uncert_scored)

        total = sum(r.contribution for r in category_results)
        risk_score = min(int(round(total)), 100)

        return AggregationResult(
            risk_score=risk_score,
            category_results=category_results,
        )

    def _score_items(self, items: List[RiskEvidenceItem]) -> List[ScoredItem]:
        """
        Score a list of items from the same category, applying:
        1. Base contribution from rule table.
        2. Correlation group diminishing returns.
        3. Confidence adjustment.
        """
        if not items:
            return []

        # Group by correlation group
        groups: Dict[str, List[RiskEvidenceItem]] = {}
        ungrouped: List[RiskEvidenceItem] = []

        for item in items:
            if item.correlation_group is not None:
                key = item.correlation_group.value
                groups.setdefault(key, []).append(item)
            else:
                ungrouped.append(item)

        scored: List[ScoredItem] = []

        # Score correlated groups
        for group_key, group_items in groups.items():
            # Sort by base contribution descending; primary gets full weight
            ordered = sorted(
                group_items,
                key=lambda i: get_base_contribution(i),
                reverse=True,
            )
            for idx, item in enumerate(ordered):
                base = get_base_contribution(item)
                corr_factor = (1.0 if idx == 0
                               else self._config.correlation_secondary_factor)
                conf_factor = self._config.confidence_factor(item.confidence)
                effective = base * corr_factor * conf_factor
                is_uncertain = (
                    item.severity.value in ("HIGH", "CRITICAL") and
                    item.confidence < self._config.confidence_low_threshold
                )
                item.is_uncertain = is_uncertain
                item.contribution = effective
                scored.append(ScoredItem(
                    item=item,
                    base_contribution=base,
                    confidence_factor=conf_factor,
                    correlation_factor=corr_factor,
                    effective_contribution=effective,
                ))

        # Score ungrouped items
        for item in ungrouped:
            base = get_base_contribution(item)
            conf_factor = self._config.confidence_factor(item.confidence)
            effective = base * conf_factor
            is_uncertain = (
                item.severity.value in ("HIGH", "CRITICAL") and
                item.confidence < self._config.confidence_low_threshold
            )
            item.is_uncertain = is_uncertain
            item.contribution = effective
            scored.append(ScoredItem(
                item=item,
                base_contribution=base,
                confidence_factor=conf_factor,
                correlation_factor=1.0,
                effective_contribution=effective,
            ))

        return scored
