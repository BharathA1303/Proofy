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
        description="'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'",
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


# ──────────────────────────────────────────────
#  Top-level response
# ──────────────────────────────────────────────

class RiskAssessmentResponse(BaseModel):
    """
    Response returned by POST /api/v1/verification/risk.
    Module 6: Risk Engine & Officer Decision Support.
    """
    verification_id: str
    document_type: str
    risk_assessment: RiskAssessmentSummary
