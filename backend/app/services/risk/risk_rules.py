"""
backend/app/services/risk/risk_rules.py

Deterministic rule engine: maps each RiskEvidenceItem to a base contribution.

Design:
  - Pure function: no I/O, no state, no randomness.
  - Operates ONLY on (signal, status, severity, confidence).
  - No document-type branches (document-specific logic lives in risk_normalizer.py).
  - Every contribution is traceable to a (signal × severity) cell in RULE_TABLE.
  - The rule engine does NOT apply confidence adjustments or category caps —
    those are the aggregator's responsibility.

Rule table structure:
  RULE_TABLE[signal][severity] → base_contribution

Base contributions represent the maximum score impact assuming full confidence.
The aggregator applies confidence_factor to scale this down for uncertain signals.
"""
from __future__ import annotations

from typing import Dict, Optional

from app.services.risk.risk_evidence import (
    EvidenceCategory,
    EvidenceSeverity,
    EvidenceStatus,
    RiskEvidenceItem,
)


# ── Base contribution rule table ──────────────────────────────────────────────
# Format: { signal_name: { severity: base_contribution } }
# NONE severity → 0.0 (positive evidence; no risk contribution)

RULE_TABLE: Dict[str, Dict[str, float]] = {

    # ── Document Structure (M1, M2) ───────────────────────────────────────
    "mrz_unavailable": {
        "CRITICAL": 10.0,
        "HIGH":      8.0,
        "MEDIUM":    5.0,
        "LOW":       2.0,
        "NONE":      0.0,
    },
    "mrz_structure_invalid": {
        "HIGH":   9.0,
        "MEDIUM": 5.0,
        "LOW":    2.0,
        "NONE":   0.0,
    },
    "critical_field_unavailable": {
        "HIGH":   6.0,
        "MEDIUM": 3.0,
        "LOW":    1.5,
        "NONE":   0.0,
    },

    # ── Document Consistency (M2) ─────────────────────────────────────────
    "viz_mrz_document_number_mismatch": {
        "CRITICAL": 20.0,
        "HIGH":     18.0,
        "MEDIUM":   10.0,
        "NONE":      0.0,
    },
    "viz_mrz_dob_mismatch": {
        "HIGH":   15.0,
        "MEDIUM":  8.0,
        "NONE":    0.0,
    },
    "viz_mrz_name_mismatch": {
        "HIGH":   10.0,
        "MEDIUM":  5.0,
        "NONE":    0.0,
    },
    "viz_mrz_consistency_failed": {
        "HIGH":   12.0,
        "MEDIUM":  6.0,
        "LOW":     2.0,
        "NONE":    0.0,
    },
    "document_number_binding_mismatch": {
        "CRITICAL": 20.0,
        "HIGH":     18.0,
        "MEDIUM":   10.0,
        "NONE":      0.0,
    },
    "document_expired": {
        "HIGH":   8.0,
        "MEDIUM": 4.0,
        "NONE":   0.0,
    },
    "visa_expired": {
        "HIGH":   8.0,
        "MEDIUM": 4.0,
        "NONE":   0.0,
    },
    "license_expired": {
        "HIGH":   8.0,
        "MEDIUM": 4.0,
        "NONE":   0.0,
    },
    "license_format_warning": {
        "MEDIUM": 5.0,
        "LOW":    2.0,
        "NONE":   0.0,
    },
    "license_registry_revoked": {
        "CRITICAL": 22.0,
        "NONE":      0.0,
    },
    "driving_license_passport_dob_mismatch": {
        "HIGH":   20.0,
        "MEDIUM": 10.0,
        "NONE":    0.0,
    },
    "driving_license_passport_name_mismatch": {
        "HIGH":   15.0,
        "MEDIUM":  8.0,
        "NONE":    0.0,
    },
    "national_id_identifier_invalid": {
        "HIGH":   12.0,
        "MEDIUM":  6.0,
        "LOW":     2.0,
        "NONE":    0.0,
    },
    "national_id_identifier_warning": {
        "MEDIUM":  5.0,
        "LOW":     2.0,
        "NONE":    0.0,
    },
    "national_id_registry_revoked": {
        "CRITICAL": 22.0,
        "NONE":      0.0,
    },
    "national_id_passport_dob_mismatch": {
        "HIGH":   20.0,
        "MEDIUM": 10.0,
        "NONE":    0.0,
    },
    "national_id_passport_name_mismatch": {
        "HIGH":   15.0,
        "MEDIUM":  8.0,
        "NONE":    0.0,
    },
    "national_id_dl_dob_mismatch": {
        "HIGH":   20.0,
        "MEDIUM": 10.0,
        "NONE":    0.0,
    },
    "national_id_dl_name_mismatch": {
        "HIGH":   15.0,
        "MEDIUM":  8.0,
        "NONE":    0.0,
    },
    "cross_document_mismatch": {
        "CRITICAL": 20.0,
        "HIGH":     18.0,
        "MEDIUM":   10.0,
        "NONE":      0.0,
    },
    "visa_passport_number_mismatch": {
        "CRITICAL": 20.0,
        "HIGH":     18.0,
        "MEDIUM":   10.0,
        "NONE":      0.0,
    },
    "cross_doc_identifier_binding_mismatch": {
        "CRITICAL": 35.0,
        "HIGH":     32.0,
        "MEDIUM":   16.0,
        "NONE":      0.0,
    },
    "passport_visa_identifier_mismatch": {
        "CRITICAL": 35.0,
        "HIGH":     32.0,
        "MEDIUM":   16.0,
        "NONE":      0.0,
    },
    "cross_doc_person_attribute_consistency_mismatch": {
        "CRITICAL": 25.0,
        "HIGH":     20.0,
        "MEDIUM":   10.0,
        "LOW":       4.0,
        "NONE":      0.0,
    },
    "cross_doc_person_name_consistency_mismatch": {
        "HIGH":     15.0,
        "MEDIUM":    8.0,
        "LOW":       3.0,
        "NONE":      0.0,
    },
    "cross_doc_person_name_consistency_partial_match": {
        "LOW":       2.0,
        "NONE":      0.0,
    },
    "cross_doc_nationality_field_consistency_mismatch": {
        "HIGH":     12.0,
        "MEDIUM":    6.0,
        "NONE":      0.0,
    },
    "date_range_invalid": {
        "CRITICAL": 18.0,
        "HIGH":     14.0,
        "MEDIUM":    8.0,
        "LOW":       3.0,
        "NONE":      0.0,
    },
    "passport_reference_invalid": {
        "HIGH":   10.0,
        "MEDIUM":  5.0,
        "NONE":    0.0,
    },
    "document_format_invalid": {
        "HIGH":   10.0,
        "MEDIUM":  5.0,
        "NONE":    0.0,
    },
    "visa_registry_revoked": {
        "CRITICAL": 22.0,
        "NONE":      0.0,
    },
    "border_permit_expired": {
        "HIGH":   10.0,
        "MEDIUM":  5.0,
        "NONE":    0.0,
    },
    "border_permit_not_yet_valid": {
        "MEDIUM":  6.0,
        "LOW":     2.0,
        "NONE":    0.0,
    },
    "border_permit_registry_revoked": {
        "CRITICAL": 22.0,
        "NONE":      0.0,
    },
    "border_permit_registry_suspended": {
        "CRITICAL": 18.0,
        "HIGH":     16.0,
        "NONE":      0.0,
    },
    "border_permit_registry_mismatch": {
        "CRITICAL": 20.0,
        "HIGH":     18.0,
        "NONE":      0.0,
    },
    "border_permit_passport_number_mismatch": {
        "CRITICAL": 35.0,
        "HIGH":     32.0,
        "MEDIUM":   16.0,
        "NONE":      0.0,
    },
    "border_permit_identifier_invalid": {
        "HIGH":   10.0,
        "MEDIUM":  5.0,
        "NONE":    0.0,
    },
    "border_permit_date_invalid": {
        "HIGH":   12.0,
        "MEDIUM":  6.0,
        "NONE":    0.0,
    },

    # ── Document Integrity / Checksums (M2) ───────────────────────────────
    "document_number_checksum_fail": {
        "HIGH":   14.0,
        "MEDIUM":  8.0,
        "LOW":     3.0,
        "NONE":    0.0,
    },
    "dob_checksum_fail": {
        "HIGH":   12.0,
        "MEDIUM":  6.0,
        "LOW":     2.0,
        "NONE":    0.0,
    },
    "expiry_checksum_fail": {
        "HIGH":   10.0,
        "MEDIUM":  5.0,
        "LOW":     2.0,
        "NONE":    0.0,
    },
    "composite_checksum_fail": {
        "HIGH":   14.0,
        "MEDIUM":  8.0,
        "LOW":     3.0,
        "NONE":    0.0,
    },

    # ── Forensic Analysis (M3) ────────────────────────────────────────────
    "forensic_high_concern": {
        "CRITICAL": 20.0,
        "HIGH":     16.0,
        "MEDIUM":    8.0,
        "NONE":      0.0,
    },
    "forensic_suspicious": {
        "HIGH":   12.0,
        "MEDIUM":  7.0,
        "LOW":     3.0,
        "NONE":    0.0,
    },
    "forensic_ela_anomaly": {
        "HIGH":   10.0,
        "MEDIUM":  6.0,
        "LOW":     2.0,
        "NONE":    0.0,
    },
    "forensic_compression_anomaly": {
        "HIGH":    8.0,
        "MEDIUM":  4.0,
        "LOW":     1.5,
        "NONE":    0.0,
    },
    "forensic_photo_boundary_anomaly": {
        "HIGH":   10.0,
        "MEDIUM":  6.0,
        "LOW":     2.0,
        "NONE":    0.0,
    },
    "forensic_metadata_anomaly": {
        "HIGH":    8.0,
        "MEDIUM":  4.0,
        "LOW":     1.5,
        "NONE":    0.0,
    },

    # ── Biometric Consistency — Face Match (M4) ───────────────────────────
    "face_match_pass": {
        "NONE": 0.0,   # Positive evidence — no contribution
    },
    "face_mismatch_high_quality": {
        "CRITICAL": 20.0,
        "HIGH":     17.0,
        "MEDIUM":    9.0,
        "NONE":      0.0,
    },
    "face_mismatch_poor_quality": {
        # Poor quality reduces severity: mismatch may be due to photo conditions,
        # not identity fraud. Confidence is already lower; aggregator handles it.
        "HIGH":   10.0,
        "MEDIUM":  6.0,
        "LOW":     3.0,
        "NONE":    0.0,
    },
    "face_detection_failed": {
        "MEDIUM":  6.0,
        "LOW":     3.0,
        "NONE":    0.0,
    },
    "face_inconclusive": {
        "MEDIUM":  5.0,
        "LOW":     2.0,
        "NONE":    0.0,
    },

    # ── Presentation Attack Detection (M4) ───────────────────────────────
    "presentation_attack_detected": {
        "CRITICAL": 20.0,
        "HIGH":     17.0,
        "NONE":      0.0,
    },
    "pad_inconclusive": {
        "MEDIUM":  5.0,
        "LOW":     2.0,
        "NONE":    0.0,
    },
    "secondary_pad_anomaly": {
        "HIGH":    8.0,
        "MEDIUM":  4.0,
        "LOW":     1.5,
        "NONE":    0.0,
    },

    # ── Registry Status (M5) ─────────────────────────────────────────────
    "registry_matched": {
        "NONE": 0.0,   # Positive evidence — no contribution
    },
    "registry_revoked": {
        "CRITICAL": 22.0,
        "NONE":      0.0,
    },
    "registry_mismatch": {
        "CRITICAL": 20.0,
        "HIGH":     18.0,
        "NONE":      0.0,
    },
    "registry_not_found": {
        "HIGH":    10.0,
        "MEDIUM":   6.0,
        "LOW":      3.0,
        "NONE":     0.0,
    },
    "registry_expired": {
        "HIGH":   10.0,
        "MEDIUM":  5.0,
        "NONE":    0.0,
    },
    "registry_suspended": {
        "CRITICAL": 18.0,
        "HIGH":     16.0,
        "NONE":      0.0,
    },
    "registry_invalid": {
        "CRITICAL": 20.0,
        "NONE":      0.0,
    },
    "registry_ambiguous": {
        "HIGH":    8.0,
        "MEDIUM":  4.0,
        "NONE":    0.0,
    },
    "registry_field_mismatch": {
        "HIGH":   12.0,
        "MEDIUM":  6.0,
        "NONE":    0.0,
    },

    # ── Verification Uncertainty ─────────────────────────────────────────
    "module_not_run": {
        "LOW":  3.0,
        "NONE": 0.0,
    },
    "module_unavailable": {
        "LOW":  3.0,
        "NONE": 0.0,
    },
    "module_timeout": {
        "LOW":  2.0,
        "NONE": 0.0,
    },
    "module_error": {
        "MEDIUM": 4.0,
        "LOW":    2.0,
        "NONE":   0.0,
    },
    "ocr_low_confidence": {
        "MEDIUM": 5.0,
        "LOW":    2.5,
        "NONE":   0.0,
    },
    "registry_provider_unavailable": {
        "LOW":  2.0,
        "NONE": 0.0,
    },
}

# Fallback for unknown signals
_FALLBACK_CONTRIBUTION: Dict[str, float] = {
    "CRITICAL": 10.0,
    "HIGH":      7.0,
    "MEDIUM":    4.0,
    "LOW":       1.5,
    "NONE":      0.0,
}


def get_base_contribution(item: RiskEvidenceItem) -> float:
    """
    Return the base contribution for a single evidence item.

    The base contribution assumes full confidence.
    The aggregator applies confidence_factor before summing.

    Returns 0.0 for:
      - severity NONE (positive or neutral evidence)
      - unavailable items (handled separately as uncertainty)
    """
    if item.severity == EvidenceSeverity.NONE:
        return 0.0

    if not item.available:
        # Unavailability contributes only to VERIFICATION_UNCERTAINTY category
        return 0.0

    severity_str = item.severity.value
    signal_rules = RULE_TABLE.get(item.signal, _FALLBACK_CONTRIBUTION)
    return signal_rules.get(severity_str, _FALLBACK_CONTRIBUTION.get(severity_str, 0.0))
