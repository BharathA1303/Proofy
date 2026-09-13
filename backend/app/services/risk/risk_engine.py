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

import hashlib
import json
import logging
from typing import Any, Dict, Optional

from app.services.documents.profiles import document_profile_registry
from app.services.risk.risk_aggregator import RiskAggregator
from app.services.risk.risk_config import RiskConfig, risk_config
from app.services.risk.risk_conflict_detector import ConflictDetector
from app.services.risk.risk_evidence import EvidenceSeverity, EvidenceStatus
from app.services.risk.risk_explanation import ExplanationBuilder
from app.services.risk.risk_normalizer import RiskNormalizer
from app.services.risk.risk_provenance import build_provenance
from app.services.risk.risk_session_store import risk_session_store

logger = logging.getLogger(__name__)


class RiskEngine:
    """
    Orchestrates the full Module 6 risk assessment pipeline.

    Composed from:
      RiskNormalizer      → M1–M7 data → List[RiskEvidenceItem]
      RiskAggregator      → evidence → scores by category
      ConflictDetector    → evidence → conflict patterns & contradictions
      ExplanationBuilder  → scores → officer reasons, top contributors, supporting evidence, limitations
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
            document_type:    Document type key (e.g. 'passport', 'driving_license').

        Returns:
            A dict matching the RiskAssessmentResponse schema.
        """
        logger.info(
            "RiskEngine: starting assessment id=%s doc_type=%s",
            verification_id, document_type,
        )

        # ── 0. Resolve Document Profile ───────────────────────────────────
        profile = None
        try:
            profile = document_profile_registry.resolve(document_type)
        except Exception:
            pass
        profile_version = profile.version if profile else "unknown"
        engine_version = "0.6.0"
        assessment_id = f"RA-{verification_id[:8]}"

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

        # ── 4. Detect conflicts and contradictions ────────────────────────
        conflict_report = self._conflict_detector.detect(evidence)

        # ── 5. Build officer explanations & contributors ──────────────────
        reasons, uncertainties = self._explainer.build_reasons(aggregation)
        top_contributors = self._explainer.build_top_contributors(aggregation)
        supporting_evidence = self._explainer.build_supporting_evidence(evidence)
        limitations = self._explainer.build_limitations(evidence)
        contradictions = conflict_report.contradictions

        # ── 6. Build provenance / completeness report ─────────────────────
        provenance = build_provenance(availability)

        # ── 7. Policy overrides & Inconclusive evaluation ─────────────────
        score = aggregation.risk_score
        critical_override_applied = False

        # Profile-driven thresholds if available
        profile_risk_cfg = getattr(profile, "risk_config", {}) or {}
        crit_thresholds = profile_risk_cfg.get("critical_thresholds", {})
        revoked_override_target = crit_thresholds.get("registry_revoked", 85)
        spoof_override_target = crit_thresholds.get("face_spoof_confirmed", 80)
        qr_override_target = crit_thresholds.get("qr_tampered", 80)

        # Evaluate critical override conditions:
        # 1. Registry revoked
        revoked_item = next(
            (e for e in evidence if e.available and e.signal == "registry_revoked" and e.status == EvidenceStatus.REVOKED),
            None
        )
        if revoked_item is not None:
            if score < revoked_override_target:
                score = revoked_override_target
                critical_override_applied = True

        # 2. Confirmed spoof / presentation attack
        spoof_item = next(
            (e for e in evidence if e.available and e.signal == "presentation_attack_detected" and e.severity == EvidenceSeverity.CRITICAL),
            None
        )
        if spoof_item is not None:
            if score < spoof_override_target:
                score = spoof_override_target
                critical_override_applied = True

        # 3. Invalid cryptographic QR signature
        qr_invalid_item = next(
            (e for e in evidence if e.available and e.signal == "qr_crypto_invalid"),
            None
        )
        if qr_invalid_item is not None:
            if score < qr_override_target:
                score = qr_override_target
                critical_override_applied = True

        # Assessment confidence computation
        if provenance.completeness == 0.0:
            assessment_confidence = 0.0
        else:
            uncert_penalty = 0.05 * len(uncertainties)
            assessment_confidence = max(0.0, min(1.0, round(provenance.completeness - uncert_penalty, 3)))

        # Compute level and recommendation
        if assessment_confidence < 0.20 and score < 50:
            level = "INCONCLUSIVE"
            recommendation = "INCONCLUSIVE - MANUAL REVIEW REQUIRED"
        else:
            level = self._config.risk_level(score)
            recommendation = self._config.officer_recommendation(level)

        # ── 8. Structured explanation text ────────────────────────────────
        explanation_text = self._explainer.build_explanation_text(
            risk_score=score,
            risk_level=level,
            officer_recommendation=recommendation,
            top_contributors=top_contributors,
            supporting_evidence=supporting_evidence,
            limitations=limitations,
            contradictions=contradictions,
            critical_override=critical_override_applied,
        )

        # ── 9. Audit snapshot hash (reproducibility) ───────────────────────
        snapshot_payload = {
            "verification_id": verification_id,
            "document_type": document_type,
            "profile_version": profile_version,
            "engine_version": engine_version,
            "risk_config_version": self._config.version,
            "risk_score": score,
            "risk_level": level,
            "evidence_signals": [
                {
                    "module": e.module,
                    "signal": e.signal,
                    "status": e.status.value,
                    "severity": e.severity.value,
                    "confidence": round(e.confidence, 4),
                }
                for e in sorted(evidence, key=lambda x: (x.module, x.signal))
            ],
        }
        snapshot_str = json.dumps(snapshot_payload, sort_keys=True)
        snapshot_hash = hashlib.sha256(snapshot_str.encode("utf-8")).hexdigest()

        # ── 10. Evidence summary counts ────────────────────────────────────
        evidence_summary = {
            "total_evaluated": len(evidence),
            "available_count": len([e for e in evidence if e.available]),
            "unavailable_count": len([e for e in evidence if not e.available]),
            "adverse_count": len([e for e in evidence if e.available and e.severity != EvidenceSeverity.NONE]),
            "positive_count": len([e for e in evidence if e.available and e.is_positive]),
            "uncertainty_count": len(uncertainties),
            "conflict_count": len(conflict_report.conflicts),
            "contradiction_count": len(contradictions),
        }

        # ── 11. Assemble response ──────────────────────────────────────────
        risk_assessment_dict = {
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

            # Section 36 fields inside risk_assessment
            "assessment_id": assessment_id,
            "profile_version": profile_version,
            "engine_version": engine_version,
            "assessment_confidence": assessment_confidence,
            "top_contributors": top_contributors,
            "supporting_evidence": supporting_evidence,
            "limitations": limitations,
            "contradictions": contradictions,
            "evidence_summary": evidence_summary,
            "explanation": explanation_text,
            "snapshot_hash": snapshot_hash,
            "critical_override_applied": critical_override_applied,
        }

        response = {
            "verification_id": verification_id,
            "document_type": document_type,
            "assessment_id": assessment_id,
            "profile_version": profile_version,
            "engine_version": engine_version,
            "risk_score": score,
            "risk_level": level,
            "assessment_confidence": assessment_confidence,
            "top_contributors": top_contributors,
            "supporting_evidence": supporting_evidence,
            "limitations": limitations,
            "contradictions": contradictions,
            "evidence_summary": evidence_summary,
            "officer_recommendation": recommendation,
            "explanation": explanation_text,
            "snapshot_hash": snapshot_hash,
            "critical_override_applied": critical_override_applied,
            "risk_assessment": risk_assessment_dict,
        }

        logger.info(
            "RiskEngine: assessment complete id=%s score=%d level=%s "
            "reasons=%d conflicts=%d completeness=%.0f%% confidence=%.2f",
            verification_id, score, level,
            len(reasons), len(conflict_report.conflicts),
            provenance.completeness * 100,
            assessment_confidence,
        )

        return response


# Singleton — shared across the application
risk_engine = RiskEngine()

