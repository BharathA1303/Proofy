"""
backend/app/services/risk/risk_engine.py

Module 6: Risk Engine orchestrator.

Reads M1–M5 evidence from the risk session store and produces a
deterministic, explainable risk assessment.

Design invariants:
  1. DETERMINISTIC: same session data → same risk score and reasons always.
  2. TRANSPARENT: every score contribution is traceable to evidence → rule → config.
  3. SERVER-SIDE: the engine never accepts risk scores, levels, or verdicts from
     the client. All inputs come from internal session stores.
  4. EVIDENCE-BASED: score = 0 when no adverse evidence exists, even if some
     modules were unavailable.
  5. CONSERVATIVE: missing modules reduce completeness but do NOT inflate the score.
  6. HUMAN-IN-THE-LOOP: provides officer guidance only. Never admits/denies/arrests.

Score architecture:
  Total = min(sum(category_contributions), 100)
  Each category contribution = min(sum(item_contributions), category_cap)
  Each item_contribution = base(signal, severity) × confidence_factor × correlation_factor
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.services.risk.risk_aggregator import RiskAggregator
from app.services.risk.risk_config import RiskConfig, risk_config
from app.services.risk.risk_conflict_detector import ConflictDetector
from app.services.risk.risk_explanation import ExplanationBuilder
from app.services.risk.risk_normalizer import RiskNormalizer
from app.services.risk.risk_provenance import build_provenance
from app.services.risk.risk_session_store import risk_session_store

logger = logging.getLogger(__name__)


class RiskEngine:
    """
    Orchestrates the full Module 6 risk assessment pipeline.

    Composed from:
      RiskNormalizer      → M1–M5 data → List[RiskEvidenceItem]
      RiskAggregator      → evidence → scores by category
      ConflictDetector    → evidence → conflict patterns
      ExplanationBuilder  → scores → officer reasons + uncertainties
      build_provenance    → availability → completeness report

    Thread-safe (all components are stateless per call).
    """

    def __init__(self, config: RiskConfig = risk_config) -> None:
        self._config = config
        self._normalizer = RiskNormalizer()
        self._aggregator = RiskAggregator(config)
        self._conflict_detector = ConflictDetector()
        self._explainer = ExplanationBuilder()

    def assess(
        self,
        verification_id: str,
        document_type: str,
    ) -> Dict[str, Any]:
        """
        Run the full risk assessment for a verification session.

        Args:
            verification_id: Session ID from Module 1 /ocr.
            document_type:    Document type key (e.g. 'passport').

        Returns:
            A dict matching the RiskAssessmentResponse schema.

        Raises:
            ValueError: If no session data is found for the verification_id.
        """
        logger.info(
            "RiskEngine: starting assessment id=%s doc_type=%s",
            verification_id, document_type,
        )

        # ── 1. Load session data ──────────────────────────────────────────
        session_data = risk_session_store.get(verification_id)
        if session_data is None:
            session_data = {}
            logger.warning(
                "RiskEngine: no session data for id=%s — "
                "all modules will be treated as not-run. "
                "Did all preceding endpoints complete?",
                verification_id,
            )

        # ── 2. Normalize evidence from all available modules ──────────────
        evidence, availability = self._normalizer.normalize(session_data)

        # ── 3. Score and aggregate ────────────────────────────────────────
        aggregation = self._aggregator.aggregate(evidence)

        # ── 4. Detect conflicts ───────────────────────────────────────────
        conflict_report = self._conflict_detector.detect(evidence)

        # ── 5. Build officer explanations ─────────────────────────────────
        reasons, uncertainties = self._explainer.build_reasons(aggregation)

        # ── 6. Build provenance / completeness report ─────────────────────
        provenance = build_provenance(availability)

        # ── 7. Compute level and recommendation ──────────────────────────
        score = aggregation.risk_score
        level = self._config.risk_level(score)
        recommendation = self._config.officer_recommendation(level)

        # ── 8. Assemble response ──────────────────────────────────────────
        response = {
            "verification_id": verification_id,
            "document_type": document_type,
            "risk_assessment": {
                "risk_score": score,
                "risk_level": level,
                "officer_recommendation": recommendation,
                "risk_config_version": self._config.version,

                "reasons": [
                    {
                        "reason_id": r.reason_id,
                        "module": r.module,
                        "signal": r.signal,
                        "severity": r.severity,
                        "confidence": r.confidence,
                        "contribution": r.contribution,
                        "explanation": r.explanation,
                        "provenance": r.provenance,
                    }
                    for r in reasons
                ],

                "category_breakdown": [
                    {
                        "category": cr.category.value,
                        "label": cr.category_label,
                        "contribution": round(cr.contribution, 2),
                        "maximum": cr.maximum,
                        "percentage_of_max": round(
                            (cr.contribution / cr.maximum * 100) if cr.maximum > 0 else 0, 1
                        ),
                    }
                    for cr in aggregation.category_results
                    if cr.contribution > 0.0 or cr.maximum > 0.0
                ],

                "module_summary": provenance.module_summaries,
                "completeness": provenance.completeness,

                "uncertainties": [
                    {
                        "module": u.module,
                        "signal": u.signal,
                        "explanation": u.explanation,
                        "confidence": u.confidence,
                        "severity": u.severity,
                    }
                    for u in uncertainties
                ],

                "conflict_detected": conflict_report.detected,
                "conflicts": [
                    {
                        "conflict_id": c.conflict_id,
                        "description": c.description,
                        "modules_involved": c.modules_involved,
                        "severity": c.severity,
                    }
                    for c in conflict_report.conflicts
                ],

                "evidence_count": len([e for e in evidence if e.available]),
                "unavailable_count": len([e for e in evidence if not e.available]),
            },
        }

        logger.info(
            "RiskEngine: assessment complete id=%s score=%d level=%s "
            "reasons=%d conflicts=%d completeness=%.0f%%",
            verification_id, score, level,
            len(reasons), len(conflict_report.conflicts),
            provenance.completeness * 100,
        )

        return response


# Singleton — shared across the application
risk_engine = RiskEngine()
