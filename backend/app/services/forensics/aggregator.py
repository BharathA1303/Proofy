"""
backend/app/services/forensics/aggregator.py

Module 3: Conservative Forensic Signal Aggregation.

Combines independent forensic signals into ONE of:
  "no_significant_anomaly"
  "suspicious"
  "high_forensic_concern"

Deterministic aggregation rule (documented, not hidden):
  A signal counts as a "weak" vote if status == "suspicious" and
  severity == "medium" (or metadata's equivalent "suspicious" status,
  which is always capped at weak — see metadata_analysis.py).

  A signal counts as a "strong" vote if status == "suspicious" and
  severity == "high".

  - strong_votes >= 2                       -> high_forensic_concern
  - strong_votes == 1                       -> suspicious
  - weak_votes   >= 2                       -> suspicious
  - weak_votes   == 1                       -> no_significant_anomaly
                                                (one weak signal alone
                                                 never escalates the result)
  - otherwise                                -> no_significant_anomaly

This deliberately requires MULTIPLE independent indicators (or one strong
one) before escalating — a single borderline ELA block or a single
compression-ratio blip must never alone produce "high_forensic_concern".
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SignalVote:
    type: str
    status: str
    severity: str


def aggregate_forensic_signals(votes: list[SignalVote]) -> tuple[str, str]:
    """
    Args:
        votes: one SignalVote per forensic technique that actually ran
               (exclude signals with status "unavailable"/"insufficient_data").

    Returns:
        (overall_assessment, explanation)
    """
    strong = [v for v in votes if v.status == "suspicious" and v.severity == "high"]
    weak = [v for v in votes if v.status == "suspicious" and v.severity == "medium"]

    if len(strong) >= 2:
        types = ", ".join(v.type.replace("_", " ") for v in strong)
        return (
            "high_forensic_concern",
            f"Multiple independent forensic indicators ({types}) identified strong "
            "anomalies. Manual review is strongly recommended.",
        )

    if len(strong) == 1:
        return (
            "suspicious",
            f"A strong forensic indicator ({strong[0].type.replace('_', ' ')}) was "
            "identified. Manual review is recommended.",
        )

    if len(weak) >= 2:
        types = ", ".join(v.type.replace("_", " ") for v in weak)
        return (
            "suspicious",
            f"Multiple independent forensic indicators ({types}) showed localized "
            "inconsistencies. Manual review is recommended.",
        )

    return (
        "no_significant_anomaly",
        "Forensic analysis did not identify significant inconsistencies at the "
        "configured sensitivity. Any single weak indicator observed is within the "
        "range expected for a genuine document.",
    )
