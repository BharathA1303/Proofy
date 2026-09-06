"""
backend/app/services/risk/risk_evidence.py

Canonical internal evidence model for Module 6: Risk Engine.

Design principles:
  - Pure Python dataclasses — no Pydantic, no ORM, no I/O.
  - EvidenceStatus and EvidenceSeverity are STRICTLY SEPARATE.
    A signal can be HIGH severity + LOW confidence.
    Do not conflate confidence with severity.
  - No verdict vocabulary: CLEARED / DENIED / FORGED / DANGEROUS are
    never used here. Risk evidence is decision-support only.
  - No raw biometric embeddings, no face image data, no model weights.
  - No demographic profiling fields (nationality/gender/race) as evidence
    categories — those appear only as document consistency check inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


# ── Status vocabulary ─────────────────────────────────────────────────────────

class EvidenceStatus(str, Enum):
    """
    Discrete outcome of a single verification signal.

    Do NOT collapse these into a boolean — the granularity is essential
    for accurate risk scoring and officer explainability.
    """
    PASS          = "PASS"
    FAIL          = "FAIL"
    WARNING       = "WARNING"
    SUSPICIOUS    = "SUSPICIOUS"
    MATCH         = "MATCH"
    MISMATCH      = "MISMATCH"
    NOT_FOUND     = "NOT_FOUND"
    EXPIRED       = "EXPIRED"
    REVOKED       = "REVOKED"
    SUSPENDED     = "SUSPENDED"
    UNAVAILABLE   = "UNAVAILABLE"
    TIMEOUT       = "TIMEOUT"
    ERROR         = "ERROR"
    INCONCLUSIVE  = "INCONCLUSIVE"
    NOT_RUN       = "NOT_RUN"


# ── Severity scale ────────────────────────────────────────────────────────────

class EvidenceSeverity(str, Enum):
    """
    Severity of an adverse evidence finding.

    NONE:     No adverse evidence. Positive or neutral signal.
    LOW:      Minor anomaly or low-impact inconsistency.
    MEDIUM:   Meaningful inconsistency requiring officer attention.
    HIGH:     Strong evidence requiring officer review.
    CRITICAL: Multiple or particularly strong indicators requiring
              urgent officer review.

    IMPORTANT: Severity describes the NATURE of the finding.
               Confidence describes HOW CERTAIN we are of that finding.
               They must remain independent.
    """
    NONE     = "NONE"
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


# ── Evidence categories ───────────────────────────────────────────────────────

class EvidenceCategory(str, Enum):
    """
    Logical grouping of evidence signals for score capping and breakdown.
    Each category has a maximum contribution (defined in RiskConfig).
    """
    DOCUMENT_STRUCTURE       = "DOCUMENT_STRUCTURE"
    DOCUMENT_CONSISTENCY     = "DOCUMENT_CONSISTENCY"
    DOCUMENT_INTEGRITY       = "DOCUMENT_INTEGRITY"
    FORENSIC_ANOMALY         = "FORENSIC_ANOMALY"
    BIOMETRIC_CONSISTENCY    = "BIOMETRIC_CONSISTENCY"
    PRESENTATION_ATTACK      = "PRESENTATION_ATTACK"
    REGISTRY_STATUS          = "REGISTRY_STATUS"
    VERIFICATION_UNCERTAINTY = "VERIFICATION_UNCERTAINTY"


# ── Correlation groups ────────────────────────────────────────────────────────

class CorrelationGroup(str, Enum):
    """
    Signals within the same group are correlated.
    The aggregator applies diminishing returns within each group to
    prevent double-counting of evidence from the same underlying event.

    Example: ELA + compression anomalies may both result from the
    same image re-save operation. Counting both at full weight inflates
    the score unjustifiably.
    """
    FORENSIC_IMAGE_SIGNALS    = "FORENSIC_IMAGE_SIGNALS"
    DOCUMENT_NUMBER_BINDING   = "DOCUMENT_NUMBER_BINDING"
    OCR_FIELD_AVAILABILITY    = "OCR_FIELD_AVAILABILITY"
    BIOMETRIC_QUALITY         = "BIOMETRIC_QUALITY"
    REGISTRY_FIELD_MISMATCHES = "REGISTRY_FIELD_MISMATCHES"
    DOB_CONSISTENCY           = "DOB_CONSISTENCY"
    NID_PASSPORT_DOB_CONSISTENCY  = "NID_PASSPORT_DOB_CONSISTENCY"
    NID_PASSPORT_NAME_CONSISTENCY = "NID_PASSPORT_NAME_CONSISTENCY"
    NID_DL_DOB_CONSISTENCY        = "NID_DL_DOB_CONSISTENCY"
    IDENTIFIER_VALIDITY           = "IDENTIFIER_VALIDITY"
    BORDER_PERMIT_PASSPORT_BINDING = "BORDER_PERMIT_PASSPORT_BINDING"
    BORDER_PERMIT_DOB_CONSISTENCY  = "BORDER_PERMIT_DOB_CONSISTENCY"


# ── Core evidence item ────────────────────────────────────────────────────────

@dataclass
class RiskEvidenceItem:
    """
    A single normalized evidence item from one verification module.

    This is the canonical unit of evidence within the risk engine.
    Every score contribution is traceable to one of these items.

    Fields:
        module:           Source module identifier ("M1", "M2", …, "M5").
        signal:           Machine-readable signal name (stable identifier for
                          rules lookup and provenance tracking).
        category:         Logical grouping for score capping.
        status:           Discrete outcome of the signal.
        severity:         Severity of an adverse finding.
        confidence:       Confidence IN THE SIGNAL MEASUREMENT, not a
                          probability of fraud or forgery. Range [0.0, 1.0].
        available:        False if the module was not run or failed to produce
                          this signal. True even if the signal value is negative.
        explanation:      Officer-facing single-sentence explanation.
        provenance:       Structured trace back to source (module, field, tool).
        contribution:     Filled by the aggregator (base × confidence_factor).
        is_uncertain:     True if this item has operationally significant
                          severity but low confidence. Flagged in uncertainties.
        correlation_group: Optional group for diminishing-returns protection.
    """
    module: str
    signal: str
    category: EvidenceCategory
    status: EvidenceStatus
    severity: EvidenceSeverity
    confidence: float
    available: bool
    explanation: str
    provenance: Dict[str, Any]
    contribution: float = 0.0
    is_uncertain: bool = False
    correlation_group: Optional[CorrelationGroup] = None


# ── Module availability ───────────────────────────────────────────────────────

@dataclass
class ModuleAvailability:
    """Tracks which verification modules contributed evidence."""
    module_id: str           # "M1" … "M5"
    label: str               # Human-readable name for UI display
    status: str              # "completed" | "partial" | "unavailable" | "not_run"
    evidence_count: int = 0  # Number of evidence items from this module
