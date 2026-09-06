"""
backend/app/services/risk/risk_provenance.py

Verification completeness and provenance tracking for the risk assessment.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from app.services.risk.risk_evidence import ModuleAvailability


@dataclass
class ProvenanceReport:
    """Module-level completeness and status for the audit trail."""
    completed_modules: List[str]
    partial_modules: List[str]
    unavailable_modules: List[str]
    not_run_modules: List[str]
    completeness: float  # 0.0–1.0
    module_summaries: List[dict]


def build_provenance(availability: List[ModuleAvailability]) -> ProvenanceReport:
    """Build a provenance report from module availability records."""
    completed, partial, unavailable, not_run = [], [], [], []

    for m in availability:
        if m.status == "completed":
            completed.append(m.module_id)
        elif m.status == "partial":
            partial.append(m.module_id)
        elif m.status == "unavailable":
            unavailable.append(m.module_id)
        else:
            not_run.append(m.module_id)

    total = len(availability)
    # partial counts as 0.5
    score = (len(completed) + 0.5 * len(partial)) / total if total > 0 else 0.0
    completeness = round(min(1.0, score), 3)

    summaries = [
        {
            "module_id": m.module_id,
            "label": m.label,
            "status": m.status,
            "evidence_count": m.evidence_count,
        }
        for m in availability
    ]

    return ProvenanceReport(
        completed_modules=completed,
        partial_modules=partial,
        unavailable_modules=unavailable,
        not_run_modules=not_run,
        completeness=completeness,
        module_summaries=summaries,
    )
