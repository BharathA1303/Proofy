"""
backend/app/services/risk/risk_config.py

Centralized, versioned risk engine configuration.

IMPORTANT:
  - All score weights, thresholds, caps, and adjustments live here.
  - Nothing is hardcoded anywhere else in the risk service.
  - All values are configurable via Settings (environment variables).
  - EVERY risk response records risk_config_version for auditability.

DISCLAIMER:
  These are initial prototype values. They have NOT been statistically
  calibrated against a representative, labelled production dataset.
  They require operational validation and calibration against realistic
  screening data before production deployment.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from app.core.config import settings
from app.services.risk.risk_evidence import EvidenceCategory


RISK_CONFIG_VERSION = "0.6.0"


@dataclass
class CategoryConfig:
    """Configuration for a single evidence category."""
    max_contribution: float   # Maximum score contribution from this category
    label: str                # Human-readable label for UI


# ── Default category caps ─────────────────────────────────────────────────────
# Sum of all caps = 145.  This means the engine cannot reach 100 from a single
# category signal alone; multiple independent adverse signals are required.
# Final score is min(sum, 100).

DEFAULT_CATEGORY_CAPS: Dict[EvidenceCategory, CategoryConfig] = {
    EvidenceCategory.DOCUMENT_STRUCTURE:       CategoryConfig(10.0,  "Document Structure"),
    EvidenceCategory.DOCUMENT_CONSISTENCY:     CategoryConfig(20.0,  "Document Consistency"),
    EvidenceCategory.DOCUMENT_INTEGRITY:       CategoryConfig(20.0,  "Document Integrity"),
    EvidenceCategory.FORENSIC_ANOMALY:         CategoryConfig(20.0,  "Forensic Analysis"),
    EvidenceCategory.BIOMETRIC_CONSISTENCY:    CategoryConfig(20.0,  "Biometric Consistency"),
    EvidenceCategory.PRESENTATION_ATTACK:      CategoryConfig(20.0,  "Presentation Attack"),
    EvidenceCategory.REGISTRY_STATUS:          CategoryConfig(25.0,  "Registry Verification"),
    EvidenceCategory.VERIFICATION_UNCERTAINTY: CategoryConfig(10.0,  "Verification Uncertainty"),
}


@dataclass
class RiskConfig:
    """
    Versioned risk engine configuration.

    One instance is created at startup and shared across all risk calculations.
    Changing any value changes the config_version or requires a re-deployment.

    All threshold/cap values can be overridden via environment variables in
    Settings (see core/config.py).
    """
    version: str = RISK_CONFIG_VERSION

    # ── Risk level thresholds ─────────────────────────────────────────────────
    # Scores below threshold_medium are LOW; between medium and high are MEDIUM, etc.
    # These are NOT legally meaningful thresholds.
    threshold_low:      int = 0
    threshold_medium:   int = 25
    threshold_high:     int = 50
    threshold_critical: int = 75

    # ── Category caps ─────────────────────────────────────────────────────────
    category_caps: Dict[EvidenceCategory, CategoryConfig] = field(
        default_factory=lambda: dict(DEFAULT_CATEGORY_CAPS)
    )

    # ── Confidence adjustment factors ─────────────────────────────────────────
    # High confidence (≥ 0.80): full weight.
    # Mid confidence (0.50 – 0.79): 85% weight.
    # Low confidence (< 0.50): 60% weight, flagged as uncertain.
    confidence_high_threshold: float = 0.80
    confidence_low_threshold:  float = 0.50
    confidence_high_factor:    float = 1.00
    confidence_mid_factor:     float = 0.85
    confidence_low_factor:     float = 0.60

    # ── Correlation group diminishing factor ──────────────────────────────────
    # Within a correlation group, the strongest signal gets 100%;
    # each additional signal gets this fraction of its computed contribution.
    correlation_secondary_factor: float = 0.50

    def cap_for(self, category: EvidenceCategory) -> float:
        """Return the max contribution cap for a category."""
        return self.category_caps.get(category, CategoryConfig(10.0, "Unknown")).max_contribution

    def label_for(self, category: EvidenceCategory) -> str:
        """Return the human-readable label for a category."""
        return self.category_caps.get(category, CategoryConfig(10.0, "Unknown")).label

    def confidence_factor(self, confidence: float) -> float:
        """
        Map a confidence value to a weighting factor.

        This prevents low-confidence signals from having the same influence
        as high-confidence signals, while NOT discarding them entirely.
        """
        if confidence >= self.confidence_high_threshold:
            return self.confidence_high_factor
        if confidence >= self.confidence_low_threshold:
            return self.confidence_mid_factor
        return self.confidence_low_factor

    def risk_level(self, score: int) -> str:
        """Map a score 0–100 to a risk level string."""
        if score >= self.threshold_critical:
            return "CRITICAL"
        if score >= self.threshold_high:
            return "HIGH"
        if score >= self.threshold_medium:
            return "MEDIUM"
        return "LOW"

    def officer_recommendation(self, level: str) -> str:
        """Map a risk level to an officer-facing review guidance string."""
        mapping = {
            "LOW":      "STANDARD OFFICER REVIEW",
            "MEDIUM":   "REVIEW REQUIRED",
            "HIGH":     "HIGH PRIORITY REVIEW",
            "CRITICAL": "CRITICAL REVIEW REQUIRED",
        }
        return mapping.get(level, "REVIEW REQUIRED")


def build_risk_config() -> RiskConfig:
    """
    Construct a RiskConfig from application settings.
    Allows environment variable overrides for all thresholds.
    """
    caps = dict(DEFAULT_CATEGORY_CAPS)

    # Allow per-category cap overrides via settings
    if hasattr(settings, "RISK_CAP_DOCUMENT_STRUCTURE"):
        caps[EvidenceCategory.DOCUMENT_STRUCTURE] = CategoryConfig(
            settings.RISK_CAP_DOCUMENT_STRUCTURE, "Document Structure"
        )
    if hasattr(settings, "RISK_CAP_REGISTRY_STATUS"):
        caps[EvidenceCategory.REGISTRY_STATUS] = CategoryConfig(
            settings.RISK_CAP_REGISTRY_STATUS, "Registry Verification"
        )

    return RiskConfig(
        version=getattr(settings, "RISK_CONFIG_VERSION", RISK_CONFIG_VERSION),
        threshold_medium=getattr(settings, "RISK_THRESHOLD_MEDIUM", 25),
        threshold_high=getattr(settings, "RISK_THRESHOLD_HIGH", 50),
        threshold_critical=getattr(settings, "RISK_THRESHOLD_CRITICAL", 75),
        category_caps=caps,
    )


# Singleton shared across the application
risk_config = build_risk_config()
