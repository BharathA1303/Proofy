"""
backend/app/schemas/risk.py

Pydantic v2 schemas for Module 6: Risk Engine & Officer Decision Support.

CRITICAL design contract:
  - RiskAssessmentResponse NEVER contains: admitted, denied, cleared, detained,
    blacklisted, forged, authentic, or any legally consequential verdict.
  - officer_recommendation is advisory ONLY and must be labeled as such in the UI.
  - risk_score is 0–100 (integer). It is NOT a probability of fraud.
  - All score contributions reference a reason_id traceable to module + signal + rule.
  - The client CANNOT submit risk_score, risk_level, reasons, or any evidence field.
    The /risk endpoint accepts only { verification_id, document_type }.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
#  Request
# ──────────────────────────────────────────────

class RiskVerifyRequest(BaseModel):
    """
    Minimal client request for Module 6 risk assessment.

    SECURITY: The client provides ONLY the session reference.
    All evidence is retrieved server-side from the risk session store.
    Any additional fields (e.g. risk_score, reasons) from the client
    are IGNORED — the server computes them independently.
    """
    verification_id: str = Field(..., description="Session ID from Module 1 /ocr")
    document_type: str = Field(..., description="Document type key (e.g. 'passport')")


# ──────────────────────────────────────────────
#  Sub-models
# ──────────────────────────────────────────────

class RiskReasonDetail(BaseModel):
    """
    A single officer-facing risk reason with full evidence provenance.
    Every reason is traceable to a specific module signal.
    """
    reason_id: str = Field(..., description="Unique identifier (e.g. 'R-M2-001')")
    module: str = Field(..., description="Source module ('M1'–'M5')")
    signal: str = Field(..., description="Machine-readable signal name")
    severity: str = Field(..., description="'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'")
    confidence: float = Field(..., description="Confidence IN this signal measurement (0.0–1.0)")
    contribution: float = Field(..., description="Score contribution after confidence adjustment")
    explanation: str = Field(..., description="Officer-facing single-sentence explanation")
    provenance: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured trace to source (module, field, tool, values)"
    )


class CategoryContributionDetail(BaseModel):
    """Score contribution from one evidence category."""
    category: str = Field(..., description="Evidence category key")
    label: str = Field(..., description="Human-readable category label")
    contribution: float = Field(..., description="Contribution after cap (0.0–max)")
    maximum: float = Field(..., description="Maximum allowed contribution for this category")
    percentage_of_max: float = Field(..., description="contribution / maximum × 100")


class ModuleSummaryItem(BaseModel):
    """Per-module availability for the verification completeness panel."""
    module_id: str = Field(..., description="Module identifier ('M1'–'M5')")
    label: str = Field(..., description="Human-readable module name")
    status: str = Field(..., description="'completed' | 'partial' | 'unavailable' | 'not_run'")
    evidence_count: int = Field(default=0, description="Number of evidence items from this module")


class UncertaintyItem(BaseModel):
    """An evidence item that is high-severity but low-confidence."""
    module: str
    signal: str
    explanation: str
    confidence: float
    severity: str


class ConflictDetail(BaseModel):
    """A detected contradiction between evidence sources."""
    conflict_id: str = Field(..., description="Conflict identifier (e.g. 'C-01')")
    description: str = Field(..., description="Officer-facing conflict description")
    modules_involved: List[str] = Field(default_factory=list)
    severity: str = Field(..., description="'warning' | 'high'")


class TopContributorDetail(BaseModel):
    """A primary contributor to the adverse risk score."""
    source_module: str = Field(..., description="Source module (e.g. 'M2', 'M3')")
    evidence_type: str = Field(..., description="Evidence type or signal identifier")
    contribution: float = Field(..., description="Risk score contribution")
    raw_value: Any = Field(default=None, description="Raw evidence value or observed metric")
    reliability: float = Field(default=1.0, description="Evidence reliability score (0.0–1.0)")
    explanation: str = Field(..., description="Officer-facing explanation")


class SupportingEvidenceDetail(BaseModel):
    """Positive corroborating finding supporting consistency or validity."""
    source_module: str = Field(..., description="Source module (e.g. 'M1', 'M7')")
    evidence_type: str = Field(..., description="Evidence type or signal identifier")
    status: str = Field(default="PASS", description="'PASS' | 'CORROBORATED' | 'AVAILABLE'")
    explanation: str = Field(..., description="Officer-facing explanation of positive finding")


class LimitationDetail(BaseModel):
    """An unrun, unconfigured, or inconclusive module/service."""
    source_module: str = Field(..., description="Source module (e.g. 'M5', 'M7')")
    limitation: str = Field(..., description="Description of the limitation or unavailable signal")
    impact: str = Field(default="MEDIUM", description="'HIGH' | 'MEDIUM' | 'LOW'")


class ContradictionDetail(BaseModel):
    """Structured discrepancy across independent evidence sources."""
    type: str = Field(default="CROSS_SOURCE_CONTRADICTION", description="Type of contradiction")
    fields: List[str] = Field(default_factory=list, description="Fields involved in the contradiction")
    sources: List[str] = Field(default_factory=list, description="Sources involved (e.g. ['ocr', 'm7_qr'])")
    severity: str = Field(default="HIGH", description="'WARNING' | 'HIGH' | 'CRITICAL'")
    explanation: str = Field(..., description="Officer-facing explanation of contradiction")


class RiskAssessmentSummary(BaseModel):
    """
    The complete Module 6 risk assessment.

    IMPORTANT: risk_score is a decision-support signal only.
    It is NOT a probability of fraud and must NOT be used as an
    automated admission or denial trigger.
    """
    risk_score: int = Field(
        ...,
        ge=0, le=100,
        description="Deterministic risk score 0–100. NOT a fraud probability.",
    )
    risk_level: str = Field(
        ...,
        description="'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | 'INCONCLUSIVE'",
    )
    officer_recommendation: str = Field(
        ...,
        description=(
            "ADVISORY officer review guidance. "
            "'STANDARD OFFICER REVIEW' | 'REVIEW REQUIRED' | "
            "'HIGH PRIORITY REVIEW' | 'CRITICAL REVIEW REQUIRED'. "
            "This is NOT a legal admission or denial decision."
        ),
    )
    risk_config_version: str = Field(
        ...,
        description="Version of the risk configuration used for this assessment.",
    )

    reasons: List[RiskReasonDetail] = Field(
        default_factory=list,
        description="Ordered list of officer-facing risk reasons (highest contribution first)",
    )
    category_breakdown: List[CategoryContributionDetail] = Field(
        default_factory=list,
        description="Per-category score contribution breakdown",
    )
    module_summary: List[ModuleSummaryItem] = Field(
        default_factory=list,
        description="Per-module verification completeness",
    )
    completeness: float = Field(
        ...,
        ge=0.0, le=1.0,
        description="Fraction of verification modules that completed (0.0–1.0)",
    )
    uncertainties: List[UncertaintyItem] = Field(
        default_factory=list,
        description="High-severity findings with below-threshold confidence",
    )
    conflict_detected: bool = Field(
        default=False,
        description="True if contradictory evidence patterns were detected across modules",
    )
    conflicts: List[ConflictDetail] = Field(
        default_factory=list,
        description="Detected contradictions between evidence sources",
    )
    evidence_count: int = Field(default=0, description="Number of available evidence items")
    unavailable_count: int = Field(default=0, description="Number of unavailable evidence items")

    # Section 36 additions
    assessment_id: Optional[str] = Field(default=None, description="Unique assessment ID")
    profile_version: Optional[str] = Field(default=None, description="Document profile version")
    engine_version: Optional[str] = Field(default="0.6.0", description="M6 Risk Engine version")
    assessment_confidence: Optional[float] = Field(default=1.0, description="Overall confidence in assessment (0.0–1.0)")
    top_contributors: List[TopContributorDetail] = Field(default_factory=list, description="Ranked adverse contributors")
    supporting_evidence: List[SupportingEvidenceDetail] = Field(default_factory=list, description="Positive corroboration")
    limitations: List[LimitationDetail] = Field(default_factory=list, description="Unavailable or unconfigured modules")
    contradictions: List[ContradictionDetail] = Field(default_factory=list, description="Cross-source discrepancies")
    evidence_summary: Dict[str, Any] = Field(default_factory=dict, description="Summary counts and evidence categories")
    explanation: Optional[str] = Field(default=None, description="Deterministic multi-paragraph officer summary")
    snapshot_hash: Optional[str] = Field(default=None, description="SHA-256 reproducibility audit hash")
    critical_override_applied: bool = Field(default=False, description="True if a critical policy override was triggered")


# ──────────────────────────────────────────────
#  Top-level response
# ──────────────────────────────────────────────

class RiskAssessmentResponse(BaseModel):
    """
    Response returned by POST /api/v1/verification/risk.
    Module 6: Risk Engine & Officer Decision Support.
    Provides dual compatibility with both root-level fields and nested risk_assessment.
    """
    verification_id: str
    document_type: str
    risk_assessment: RiskAssessmentSummary

    # Section 36 root-level fields
    assessment_id: Optional[str] = None
    profile_version: Optional[str] = None
    engine_version: Optional[str] = None
    risk_score: Optional[int] = None
    risk_level: Optional[str] = None
    assessment_confidence: Optional[float] = None
    top_contributors: List[TopContributorDetail] = Field(default_factory=list)
    supporting_evidence: List[SupportingEvidenceDetail] = Field(default_factory=list)
    limitations: List[LimitationDetail] = Field(default_factory=list)
    contradictions: List[ContradictionDetail] = Field(default_factory=list)
    evidence_summary: Dict[str, Any] = Field(default_factory=dict)
    officer_recommendation: Optional[str] = None
    explanation: Optional[str] = None
    snapshot_hash: Optional[str] = None
    critical_override_applied: bool = False

    def model_post_init(self, __context: Any) -> None:
        if self.risk_assessment is not None:
            if self.risk_score is None:
                self.risk_score = self.risk_assessment.risk_score
            if self.risk_level is None:
                self.risk_level = self.risk_assessment.risk_level
            if self.officer_recommendation is None:
                self.officer_recommendation = self.risk_assessment.officer_recommendation
            if self.assessment_id is None:
                self.assessment_id = self.risk_assessment.assessment_id
            if self.profile_version is None:
                self.profile_version = self.risk_assessment.profile_version
            if self.engine_version is None:
                self.engine_version = self.risk_assessment.engine_version
            if self.assessment_confidence is None:
                self.assessment_confidence = self.risk_assessment.assessment_confidence
            if not self.top_contributors:
                self.top_contributors = self.risk_assessment.top_contributors
            if not self.supporting_evidence:
                self.supporting_evidence = self.risk_assessment.supporting_evidence
            if not self.limitations:
                self.limitations = self.risk_assessment.limitations
            if not self.contradictions:
                self.contradictions = self.risk_assessment.contradictions
            if not self.evidence_summary:
                self.evidence_summary = self.risk_assessment.evidence_summary
            if self.explanation is None:
                self.explanation = self.risk_assessment.explanation
            if self.snapshot_hash is None:
                self.snapshot_hash = self.risk_assessment.snapshot_hash
            if not self.critical_override_applied:
                self.critical_override_applied = self.risk_assessment.critical_override_applied
