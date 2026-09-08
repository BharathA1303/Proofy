"""
backend/app/schemas/quality.py

Pydantic schemas for the Pre-OCR Document Quality Gate.
"""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class DocumentQualityMetrics(BaseModel):
    """Granular normalized 0-100% metrics for individual optical quality dimensions."""
    resolution: int = Field(..., ge=0, le=100, description="Resolution and scale adequacy (0-100%)")
    sharpness: int = Field(..., ge=0, le=100, description="Edge sharpness and blur resistance (0-100%)")
    brightness: int = Field(..., ge=0, le=100, description="Even illumination and exposure (0-100%)")
    contrast: int = Field(..., ge=0, le=100, description="Dynamic range between text and background (0-100%)")
    glare: int = Field(..., ge=0, le=100, description="Freedom from specular flash reflections (0-100%)")


class DocumentQualityResponse(BaseModel):
    """Top-level document quality assessment response."""
    status: str = Field(..., description="'acceptable' | 'warning' | 'poor'")
    is_acceptable: bool = Field(..., description="Whether document is safe for automated inspection")
    overall_score: int = Field(..., ge=0, le=100, description="Composite optical quality index (0-100%)")
    metrics: DocumentQualityMetrics
    width: int
    height: int
    reasons: List[str] = Field(default_factory=list, description="Specific quality flags or issues identified")
    guidance: str = Field(..., description="Actionable capture instructions for the officer or traveler")
    error_code: Optional[str] = Field(None, description="Standardized error code if quality is rejected")
