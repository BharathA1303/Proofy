"""
backend/app/schemas/forensics.py

Pydantic v2 schemas for Module 3: Tampering & Forensic Analysis.

IMPORTANT — terminology contract with the frontend:
  - "confidence" on a signal means confidence IN THE MEASUREMENT, never a
    probability of forgery.
  - overall_assessment is one of:
      "no_significant_anomaly" | "suspicious" | "high_forensic_concern"
      | "insufficient_data"
    It is NEVER "forged" / "authentic" / a numeric risk score.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field

from app.schemas.evidence import NormalizedEvidenceItem


class PhotoRegionBox(BaseModel):
    """Coordinates are relative to the original uploaded image."""
    x: int
    y: int
    width: int
    height: int


class ForensicSignal(BaseModel):
    """One independently-computed forensic indicator."""
    type: str = Field(..., description="e.g. 'ela' | 'photo_boundary' | 'compression' | 'metadata'")
    status: str = Field(..., description="'normal' | 'suspicious' | 'unavailable' | 'insufficient_data' | signal-specific value")
    severity: str = Field(..., description="'low' | 'medium' | 'high'")
    confidence: float = Field(..., description="Confidence in this measurement — NOT a forgery probability.")
    description: str
    region: Optional[PhotoRegionBox] = None
    metrics: dict = Field(default_factory=dict, description="Raw numeric evidence for this signal.")


class ForensicAnalysisSummary(BaseModel):
    """The complete Module 3 result."""
    status: str = Field(..., description="'completed' | 'insufficient_data'")
    overall_assessment: str = Field(
        ...,
        description="'no_significant_anomaly' | 'suspicious' | 'high_forensic_concern' | 'insufficient_data'",
    )
    explanation: str
    signals: list[ForensicSignal] = Field(default_factory=list)
    photo_region: Optional[PhotoRegionBox] = None
    quality_reasons: list[str] = Field(default_factory=list)
    evidence_items: list[NormalizedEvidenceItem] = Field(
        default_factory=list,
        description=(
            "Escalated, typed evidence items raised by individual forensic "
            "techniques (e.g. a fallback-tier photo boundary variance anomaly). "
            "Additive to `signals` — never removes or replaces a signal entry."
        ),
    )


class ForensicAnalysisResponse(BaseModel):
    verification_id: str
    document_type: str
    forensic_analysis: ForensicAnalysisSummary
