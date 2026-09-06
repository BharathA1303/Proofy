"""
backend/app/services/case/case_risk.py

Case-Level Risk Evaluator.
Aggregates normalized evidence from all documents within a verification case,
incorporates cross-document intelligence with double-counting protection,
and produces explainable officer decision support.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Set, Tuple

from app.schemas.case import CaseRiskAssessment
from app.services.case.case_audit import CaseEventType
from app.services.case.verification_case import VerificationCase
from app.services.risk.risk_aggregator import RiskAggregator
from app.services.risk.risk_config import RiskConfig, risk_config
from app.services.risk.risk_conflict_detector import ConflictDetector
from app.services.risk.risk_evidence import (
    CorrelationGroup,
    EvidenceSeverity,
    RiskEvidenceItem,
)
from app.services.risk.risk_explanation import ExplanationBuilder
from app.services.risk.risk_normalizer import RiskNormalizer
from app.services.risk.risk_provenance import build_provenance
from app.services.risk.risk_session_store import risk_session_store

logger = logging.getLogger(__name__)


class CaseRiskEvaluator:
    """Evaluates case-level composite risk across multiple documents."""

    def __init__(self, config: RiskConfig = risk_config) -> None:
        self._config = config
        self._normalizer = RiskNormalizer()
        self._aggregator = RiskAggregator(config)
        self._conflict_detector = ConflictDetector()
        self._explainer = ExplanationBuilder()

    def evaluate_case_risk(self, case: VerificationCase) -> Dict[str, Any]:
        """
        Evaluate unified risk across all active documents in the case.
        """
        active_docs = case.get_active_documents()
        documents_considered = [doc.document_id for doc in active_docs]

        all_evidence: List[RiskEvidenceItem] = []
        doc_completeness_list: List[float] = []

        # 1. Gather normalized evidence from all documents
        for doc in active_docs:
            session_data = risk_session_store.get(doc.verification_id) or {}
            ev_list, availability = self._normalizer.normalize(session_data)
            all_evidence.extend(ev_list)

            # Compute completeness for this document
            prov = build_provenance(availability)
            doc_completeness_list.append(prov.completeness)

        # 2. Add cross-document relationship evidence
        all_evidence.extend(case.cross_document_evidence)

        # 3. Apply double-counting protection / deduplication
        deduped_evidence = self._deduplicate_evidence(all_evidence)

        # 4. Compute composite completeness (average across documents)
        case_completeness = (
            sum(doc_completeness_list) / len(doc_completeness_list)
            if doc_completeness_list else 1.0
        )

        # 5. Aggregate score
        aggregation = self._aggregator.aggregate(deduped_evidence)

        # 6. Detect conflicts across all evidence
        conflicts = self._conflict_detector.detect(deduped_evidence)

        # 7. Generate officer reasons
        reasons, uncertainties = self._explainer.build_reasons(aggregation)

        # 8. Score, level, recommendation
        score = aggregation.risk_score
        level = self._config.risk_level(score)
        recommendation = self._config.officer_recommendation(level)

        has_conflict = bool(conflicts.conflicts) or any(
            getattr(rel.status, "value", str(rel.status)) == "MISMATCH" and rel.severity in ("HIGH", "CRITICAL")
            for rel in case.relationships
        )

        assessment = {
            "risk_score": score,
            "risk_level": level,
            "officer_recommendation": recommendation,
            "recommendation": recommendation,
            "documents_considered": documents_considered,
            "cross_document_evidence": [rel.model_dump() for rel in case.relationships],
            "conflict_detected": has_conflict,
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
            "conflicts": [
                {
                    "conflict_id": c.conflict_id,
                    "description": c.description,
                    "modules_involved": c.modules_involved,
                    "severity": c.severity,
                }
                for c in conflicts.conflicts
            ],
            "verification_completeness": round(case_completeness, 2),
            "risk_config_version": self._config.version,
        }

        case.risk_assessment = assessment
        case.record_event(
            CaseEventType.CASE_RISK_RECALCULATED,
            details={"score": score, "level": level},
        )

        return assessment

    def _deduplicate_evidence(
        self,
        items: List[RiskEvidenceItem],
    ) -> List[RiskEvidenceItem]:
        """
        Prevent double-counting of the same underlying identity fact across modules.
        Example: If M2 emitted cross_document_mismatch and CrossDocumentEngine
        also emitted cross_doc_identifier_binding_mismatch for the same binding,
        we retain only one primary item in the DOCUMENT_NUMBER_BINDING correlation group.
        """
        seen_binding_signals: Set[str] = set()
        deduped: List[RiskEvidenceItem] = []

        for item in items:
            # Handle identifier binding duplicate check
            if item.correlation_group == CorrelationGroup.DOCUMENT_NUMBER_BINDING:
                binding_key = f"{item.category.value}:{item.correlation_group.value}"
                if binding_key in seen_binding_signals:
                    # Downgrade or skip duplicate item to prevent inflation
                    logger.debug(
                        "CaseRiskEvaluator: deduplicated redundant binding signal %s",
                        item.signal,
                    )
                    continue
                seen_binding_signals.add(binding_key)

            deduped.append(item)

        return deduped


case_risk_evaluator = CaseRiskEvaluator()
