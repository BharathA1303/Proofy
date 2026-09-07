"""
backend/app/services/risk/risk_normalizer.py

Module evidence normalizer: converts raw M1–M5 session data into
a flat list of canonical RiskEvidenceItems.

Design:
  - Document-specific logic is ONLY here. The engine, aggregator, and rules
    are all document-agnostic. Adding a new document type only requires
    extending the normalizer methods.
  - The normalizer never fabricates evidence for missing modules.
    If a module's data is absent, it returns unavailability items.
  - Severity is assigned based on CONTEXT:
    e.g. face mismatch + poor quality → lower severity than
         face mismatch + good quality (not the same finding).
  - Confidence describes certainty of the SIGNAL, not probability of fraud.

Module data is read from the session_data dict populated by risk_session_store:
  {
    "m1_ocr":        { ... },
    "m2_validation": { ... },
    "m3_forensics":  { ... },
    "m4_biometrics": { ... },
    "m5_registry":   { ... },
  }
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.services.risk.risk_evidence import (
    CorrelationGroup,
    EvidenceCategory,
    EvidenceSeverity,
    EvidenceStatus,
    ModuleAvailability,
    RiskEvidenceItem,
)

logger = logging.getLogger(__name__)


def _item(
    module: str,
    signal: str,
    category: EvidenceCategory,
    status: EvidenceStatus,
    severity: EvidenceSeverity,
    confidence: float,
    explanation: str,
    provenance: Dict[str, Any],
    available: bool = True,
    correlation_group: Optional[CorrelationGroup] = None,
) -> RiskEvidenceItem:
    """Convenience factory for RiskEvidenceItem."""
    return RiskEvidenceItem(
        module=module,
        signal=signal,
        category=category,
        status=status,
        severity=severity,
        confidence=max(0.0, min(1.0, confidence)),
        available=available,
        explanation=explanation,
        provenance=provenance,
        correlation_group=correlation_group,
    )


def _unavailable(
    module: str,
    signal: str,
    category: EvidenceCategory,
    explanation: str,
    source: str,
) -> RiskEvidenceItem:
    """Create a standard unavailability item."""
    return _item(
        module=module,
        signal=signal,
        category=EvidenceCategory.VERIFICATION_UNCERTAINTY,
        status=EvidenceStatus.UNAVAILABLE,
        severity=EvidenceSeverity.LOW,
        confidence=1.0,
        explanation=explanation,
        provenance={"source": source, "module": module},
        available=False,
    )


# ── M1 — OCR ──────────────────────────────────────────────────────────────────

def normalize_ocr(m1_data: Optional[Dict[str, Any]]) -> List[RiskEvidenceItem]:
    """
    Normalize Module 1 OCR metadata into risk evidence items.

    OCR evidence is primarily about UNCERTAINTY, not fraud:
    - Low OCR confidence → increases verification uncertainty
    - Missing MRZ → increases uncertainty (M2 checksums cannot run)
    - Missing critical fields → increases uncertainty

    Low OCR confidence must NEVER be interpreted as forgery evidence alone.
    """
    if not m1_data:
        return [_unavailable("M1", "ocr_unavailable", EvidenceCategory.VERIFICATION_UNCERTAINTY,
                             "Module 1 (OCR) did not complete. Verification is incomplete.",
                             "ocr_engine")]

    items: List[RiskEvidenceItem] = []
    prov = {"source": "paddleocr_engine", "module": "M1"}

    overall_conf = m1_data.get("overall_confidence") or 0.0
    has_low_conf = m1_data.get("has_low_confidence_regions", False)
    mrz_available = m1_data.get("mrz_available", False)
    critical_fields_missing = m1_data.get("critical_fields_missing", [])
    ocr_status = m1_data.get("status", "unknown")

    # OCR engine failure
    if ocr_status == "failed":
        items.append(_item(
            module="M1", signal="ocr_unavailable",
            category=EvidenceCategory.VERIFICATION_UNCERTAINTY,
            status=EvidenceStatus.ERROR,
            severity=EvidenceSeverity.MEDIUM,
            confidence=1.0,
            explanation="OCR engine failed to extract meaningful text from the document.",
            provenance=prov,
            available=False,
        ))
        return items

    # Low OCR confidence
    if has_low_conf or overall_conf < 0.65:
        severity = EvidenceSeverity.MEDIUM if overall_conf < 0.50 else EvidenceSeverity.LOW
        items.append(_item(
            module="M1", signal="ocr_low_confidence",
            category=EvidenceCategory.VERIFICATION_UNCERTAINTY,
            status=EvidenceStatus.WARNING,
            severity=severity,
            confidence=0.95,
            explanation=f"OCR confidence is below threshold (overall: {overall_conf:.0%}). "
                        "Extracted field values may be unreliable.",
            provenance={**prov, "overall_confidence": overall_conf},
        ))

    # MRZ unavailable (only if applicable to the document type)
    mrz_applicable = m1_data.get("mrz_applicable", True)
    if not mrz_available and mrz_applicable:
        items.append(_item(
            module="M1", signal="mrz_unavailable",
            category=EvidenceCategory.DOCUMENT_STRUCTURE,
            status=EvidenceStatus.FAIL,
            severity=EvidenceSeverity.HIGH,
            confidence=0.95,
            explanation="Machine Readable Zone (MRZ) was not detected in the document image. "
                        "ICAO checksum validation cannot be performed.",
            provenance=prov,
        ))

    # Critical fields missing
    for field_name in critical_fields_missing:
        items.append(_item(
            module="M1", signal="critical_field_unavailable",
            category=EvidenceCategory.DOCUMENT_STRUCTURE,
            status=EvidenceStatus.FAIL,
            severity=EvidenceSeverity.MEDIUM,
            confidence=0.90,
            explanation=f"Critical identity field '{field_name}' could not be extracted.",
            provenance={**prov, "field": field_name},
            correlation_group=CorrelationGroup.OCR_FIELD_AVAILABILITY,
        ))

    return items


# ── M2 — Document Validation ──────────────────────────────────────────────────

def normalize_validation(m2_data: Optional[Dict[str, Any]]) -> List[RiskEvidenceItem]:
    """
    Normalize Module 2 document validation checks.

    Key design decisions:
    - Checksum failure is NOT automatic fraud — OCR noise can cause failures.
      The normalizer adjusts confidence based on overall OCR quality where possible.
    - VIZ/MRZ document number mismatch is a CRITICAL Passport Number Binding Trap
      violation and carries the highest consistency weight.
    - Expiry is an administrative finding, not a forgery indicator.
    - Supports both Passport and Visa structural validation evidence through
      canonical risk categories.
    """
    if not m2_data:
        return [_unavailable("M2", "module_not_run",
                             EvidenceCategory.VERIFICATION_UNCERTAINTY,
                             "Module 2 (Document Validation) did not run.",
                             "passport_validation_service")]

    items: List[RiskEvidenceItem] = []
    checks = m2_data.get("checks", {})
    prov_base = {"source": m2_data.get("validator_source", "validation_service"), "module": "M2"}

    def p(extra=None):
        return {**prov_base, **(extra or {})}

    # ── Passport Check 1: MRZ structure
    mrz = checks.get("mrz_structure", {})
    if mrz and not mrz.get("valid", True):
        items.append(_item(
            module="M2", signal="mrz_structure_invalid",
            category=EvidenceCategory.DOCUMENT_STRUCTURE,
            status=EvidenceStatus.FAIL,
            severity=EvidenceSeverity.HIGH,
            confidence=0.95,
            explanation=mrz.get("message", "MRZ TD3 structure is invalid."),
            provenance=p({"check": "mrz_structure"}),
        ))

    # ── Passport Check 2: Document number checksum
    doc_chk = checks.get("document_number_checksum", {})
    if doc_chk and not doc_chk.get("valid", True):
        items.append(_item(
            module="M2", signal="document_number_checksum_fail",
            category=EvidenceCategory.DOCUMENT_INTEGRITY,
            status=EvidenceStatus.FAIL,
            severity=EvidenceSeverity.HIGH,
            confidence=0.90,
            explanation=f"Document number check digit mismatch. "
                        f"Computed: {doc_chk.get('computed')}, "
                        f"MRZ: {doc_chk.get('actual')}.",
            provenance=p({"check": "document_number_checksum",
                         "computed": doc_chk.get("computed"),
                         "actual": doc_chk.get("actual")}),
        ))

    # ── Passport Check 3: DOB checksum
    dob_chk = checks.get("dob_checksum", {})
    if dob_chk and not dob_chk.get("valid", True):
        items.append(_item(
            module="M2", signal="dob_checksum_fail",
            category=EvidenceCategory.DOCUMENT_INTEGRITY,
            status=EvidenceStatus.FAIL,
            severity=EvidenceSeverity.HIGH,
            confidence=0.90,
            explanation=f"Date of birth check digit mismatch. "
                        f"Computed: {dob_chk.get('computed')}, "
                        f"MRZ: {dob_chk.get('actual')}.",
            provenance=p({"check": "dob_checksum"}),
        ))

    # ── Passport Check 4: Expiry checksum
    exp_chk = checks.get("expiry_checksum", {})
    if exp_chk and not exp_chk.get("valid", True):
        items.append(_item(
            module="M2", signal="expiry_checksum_fail",
            category=EvidenceCategory.DOCUMENT_INTEGRITY,
            status=EvidenceStatus.FAIL,
            severity=EvidenceSeverity.MEDIUM,
            confidence=0.90,
            explanation=f"Expiry date check digit mismatch. "
                        f"Computed: {exp_chk.get('computed')}, "
                        f"MRZ: {exp_chk.get('actual')}.",
            provenance=p({"check": "expiry_checksum"}),
        ))

    # ── Passport Check 5: Composite checksum
    comp_chk = checks.get("composite_checksum", {})
    if comp_chk and not comp_chk.get("valid", True):
        items.append(_item(
            module="M2", signal="composite_checksum_fail",
            category=EvidenceCategory.DOCUMENT_INTEGRITY,
            status=EvidenceStatus.FAIL,
            severity=EvidenceSeverity.HIGH,
            confidence=0.90,
            explanation="Composite check digit mismatch. Multiple fields may be corrupted.",
            provenance=p({"check": "composite_checksum"}),
        ))

    # ── Universal Check: Expiry date
    expiry = checks.get("expiry_date", {})
    if expiry.get("expired"):
        items.append(_item(
            module="M2", signal="document_expired",
            category=EvidenceCategory.DOCUMENT_CONSISTENCY,
            status=EvidenceStatus.EXPIRED,
            severity=EvidenceSeverity.HIGH,
            confidence=0.99,
            explanation=f"Document has expired: {expiry.get('expiry_date', 'unknown date')}.",
            provenance=p({"check": "expiry_date", "expiry_date": expiry.get("expiry_date")}),
        ))

    # ── Passport Check 6: Passport Number Binding Trap
    binding = checks.get("passport_number_binding", {})
    if binding and binding.get("match") is False:
        items.append(_item(
            module="M2", signal="document_number_binding_mismatch",
            category=EvidenceCategory.DOCUMENT_CONSISTENCY,
            status=EvidenceStatus.MISMATCH,
            severity=EvidenceSeverity.CRITICAL,
            confidence=0.99,
            explanation=f"Critical: Passport Number Binding Trap violation. "
                        f"VIZ={binding.get('viz_value')} ≠ MRZ={binding.get('mrz_value')}.",
            provenance=p({"check": "passport_number_binding",
                         "viz_value": binding.get("viz_value"),
                         "mrz_value": binding.get("mrz_value")}),
            correlation_group=CorrelationGroup.DOCUMENT_NUMBER_BINDING,
        ))

    # ── Passport Check 7: VIZ ↔ MRZ field consistency
    viz_mrz = checks.get("viz_mrz_consistency", {})
    viz_status = viz_mrz.get("status", "unknown")
    fields_data = viz_mrz.get("fields", {})

    if viz_status in ("failed", "warning"):
        for field_name, fdata in fields_data.items():
            f_match = fdata.get("match") if isinstance(fdata, dict) else getattr(fdata, "match", None)
            if f_match is False:
                f_viz = fdata.get("viz") if isinstance(fdata, dict) else getattr(fdata, "viz", None)
                f_mrz = fdata.get("mrz") if isinstance(fdata, dict) else getattr(fdata, "mrz", None)
                sev = (EvidenceSeverity.HIGH if field_name in ("document_number", "date_of_birth")
                       else EvidenceSeverity.MEDIUM)
                signal = (
                    "viz_mrz_document_number_mismatch" if field_name == "document_number"
                    else "viz_mrz_dob_mismatch" if field_name == "date_of_birth"
                    else "viz_mrz_name_mismatch" if field_name == "name"
                    else "viz_mrz_consistency_failed"
                )
                cg = (CorrelationGroup.DOCUMENT_NUMBER_BINDING
                      if field_name == "document_number" else None)
                items.append(_item(
                    module="M2", signal=signal,
                    category=EvidenceCategory.DOCUMENT_CONSISTENCY,
                    status=EvidenceStatus.MISMATCH,
                    severity=sev,
                    confidence=0.95,
                    explanation=f"VIZ/MRZ mismatch on '{field_name}': "
                                f"VIZ={f_viz}, MRZ={f_mrz}.",
                    provenance=p({"check": "viz_mrz_consistency", "field": field_name,
                                 "viz": f_viz, "mrz": f_mrz}),
                    correlation_group=cg,
                ))

    # ── Visa / Generic Structural Check 1: Required Fields
    req_fields = checks.get("required_fields", {})
    if req_fields and req_fields.get("valid") is False:
        items.append(_item(
            module="M2", signal="critical_field_unavailable",
            category=EvidenceCategory.DOCUMENT_STRUCTURE,
            status=EvidenceStatus.FAIL,
            severity=EvidenceSeverity.HIGH,
            confidence=0.95,
            explanation=req_fields.get("message", "Required credential fields are missing."),
            provenance=p({"check": "required_fields"}),
        ))

    # ── Visa / Generic Structural Check 2: Date Chronology
    date_chron = checks.get("date_chronology", {})
    if date_chron and date_chron.get("valid") is False:
        items.append(_item(
            module="M2", signal="date_range_invalid",
            category=EvidenceCategory.DOCUMENT_INTEGRITY,
            status=EvidenceStatus.FAIL,
            severity=EvidenceSeverity.HIGH,
            confidence=0.95,
            explanation=date_chron.get("message", "Date range or chronology is invalid."),
            provenance=p({"check": "date_chronology"}),
        ))

    # ── Visa / Generic Structural Check 3: Credential Number Format
    visa_num_chk = checks.get("visa_number_format", {})
    if visa_num_chk and visa_num_chk.get("valid") is False:
        items.append(_item(
            module="M2", signal="document_format_invalid",
            category=EvidenceCategory.DOCUMENT_STRUCTURE,
            status=EvidenceStatus.WARNING,
            severity=EvidenceSeverity.MEDIUM,
            confidence=0.90,
            explanation=visa_num_chk.get("message", "Credential number format irregular."),
            provenance=p({"check": "visa_number_format"}),
        ))

    # ── Visa / Generic Structural Check 4: Passport Reference Format
    ppt_ref_chk = checks.get("passport_reference", {})
    if ppt_ref_chk and ppt_ref_chk.get("valid") is False:
        items.append(_item(
            module="M2", signal="passport_reference_invalid",
            category=EvidenceCategory.DOCUMENT_STRUCTURE,
            status=EvidenceStatus.WARNING,
            severity=EvidenceSeverity.MEDIUM,
            confidence=0.85,
            explanation=ppt_ref_chk.get("message", "Passport reference format irregular."),
            provenance=p({"check": "passport_reference"}),
        ))

    # ── Cross-Document Relationships
    cross_chk = checks.get("cross_document_passport", {})
    if cross_chk and (cross_chk.get("status") in ("failed", "MISMATCH") or cross_chk.get("valid") is False):
        items.append(_item(
            module="M2", signal="cross_document_mismatch",
            category=EvidenceCategory.DOCUMENT_CONSISTENCY,
            status=EvidenceStatus.MISMATCH,
            severity=EvidenceSeverity.CRITICAL,
            confidence=0.98,
            explanation=cross_chk.get("message", "Cross-document field mismatch detected."),
            provenance=p({"check": "cross_document_passport"}),
        ))

    relationships = m2_data.get("relationships") or []
    if isinstance(relationships, dict):
        relationships = [relationships]
    for rel in relationships:
        if rel.get("status") == "MISMATCH":
            items.append(_item(
                module="M2", signal="cross_document_mismatch",
                category=EvidenceCategory.DOCUMENT_CONSISTENCY,
                status=EvidenceStatus.MISMATCH,
                severity=EvidenceSeverity.CRITICAL,
                confidence=0.98,
                explanation=rel.get("explanation", "Cross-document field mismatch detected."),
                provenance=p({"relationship": rel}),
            ))
    return items


# ── M3 — Forensics ────────────────────────────────────────────────────────────

_FORENSIC_SIGNAL_MAP = {
    "ela":            "forensic_ela_anomaly",
    "compression":    "forensic_compression_anomaly",
    "photo_boundary": "forensic_photo_boundary_anomaly",
    "metadata":       "forensic_metadata_anomaly",
}

def normalize_forensics(m3_data: Optional[Dict[str, Any]]) -> List[RiskEvidenceItem]:
    """
    Normalize Module 3 forensic analysis results.

    Correlation protection: ELA + compression + metadata are in one
    correlation group (FORENSIC_IMAGE_SIGNALS) because they may all result
    from a single image re-save event. Photo boundary is independent.

    IMPORTANT: 'suspicious' forensic signals do NOT equal forgery probability.
    They are optical/compression anomalies requiring officer attention.
    """
    if not m3_data:
        return [_unavailable("M3", "module_not_run",
                             EvidenceCategory.VERIFICATION_UNCERTAINTY,
                             "Module 3 (Forensic Analysis) did not run.",
                             "forensic_service")]

    items: List[RiskEvidenceItem] = []
    overall = m3_data.get("overall_assessment", "insufficient_data")
    prov_base = {"source": "forensic_service", "module": "M3"}

    if overall == "insufficient_data":
        items.append(_item(
            module="M3", signal="module_not_run",
            category=EvidenceCategory.VERIFICATION_UNCERTAINTY,
            status=EvidenceStatus.INCONCLUSIVE,
            severity=EvidenceSeverity.LOW,
            confidence=1.0,
            explanation="Forensic analysis was inconclusive due to insufficient image quality.",
            provenance=prov_base,
            available=False,
        ))
        return items

    signals = m3_data.get("signals", [])

    for sig in signals:
        sig_type = sig.get("type", "unknown")
        sig_status = sig.get("status", "normal")
        sig_severity = sig.get("severity", "low")
        sig_confidence = float(sig.get("confidence", 0.7))
        sig_desc = sig.get("description", f"Forensic signal: {sig_type}.")

        if sig_status not in ("suspicious",):
            continue  # only adverse signals generate evidence items

        signal_name = _FORENSIC_SIGNAL_MAP.get(sig_type, "forensic_suspicious")

        # Correlation group: ELA + compression + metadata are correlated
        cg = (CorrelationGroup.FORENSIC_IMAGE_SIGNALS
              if sig_type in ("ela", "compression", "metadata") else None)

        sev_map = {"low": EvidenceSeverity.LOW, "medium": EvidenceSeverity.MEDIUM,
                   "high": EvidenceSeverity.HIGH}
        sev = sev_map.get(sig_severity, EvidenceSeverity.MEDIUM)

        items.append(_item(
            module="M3", signal=signal_name,
            category=EvidenceCategory.FORENSIC_ANOMALY,
            status=EvidenceStatus.SUSPICIOUS,
            severity=sev,
            confidence=sig_confidence,
            explanation=sig_desc,
            provenance={**prov_base, "signal_type": sig_type, "signal_status": sig_status},
            correlation_group=cg,
        ))

    # High-level overall assessment item (non-correlated)
    if overall == "high_forensic_concern":
        items.append(_item(
            module="M3", signal="forensic_high_concern",
            category=EvidenceCategory.FORENSIC_ANOMALY,
            status=EvidenceStatus.SUSPICIOUS,
            severity=EvidenceSeverity.HIGH,
            confidence=0.80,
            explanation="Forensic analysis indicates significant image-level anomalies.",
            provenance=prov_base,
        ))
    elif overall == "suspicious":
        items.append(_item(
            module="M3", signal="forensic_suspicious",
            category=EvidenceCategory.FORENSIC_ANOMALY,
            status=EvidenceStatus.SUSPICIOUS,
            severity=EvidenceSeverity.MEDIUM,
            confidence=0.75,
            explanation="Forensic analysis detected image anomalies requiring officer attention.",
            provenance=prov_base,
        ))

    return items


# ── M4 — Biometrics ───────────────────────────────────────────────────────────

def normalize_biometrics(m4_data: Optional[Dict[str, Any]]) -> List[RiskEvidenceItem]:
    """
    Normalize Module 4 biometric verification results.

    Severity is context-dependent:
    - Face mismatch + acceptable quality → HIGH severity
    - Face mismatch + poor quality → MEDIUM severity (ambiguous — may be
      camera/lighting/document wear, not identity substitution)
    - Presentation attack → CRITICAL severity
    - Face unavailable → LOW uncertainty

    IMPORTANT: Face similarity below threshold ≠ fake identity.
    Quality context must be considered.
    """
    if not m4_data:
        return [_unavailable("M4", "module_not_run",
                             EvidenceCategory.VERIFICATION_UNCERTAINTY,
                             "Module 4 (Biometric Verification) did not run.",
                             "face_verification_service")]

    items: List[RiskEvidenceItem] = []
    overall = m4_data.get("overall_assessment", "")
    prov_base = {"source": "face_verification_service", "module": "M4"}

    doc_face = m4_data.get("document_face", {})
    live_face = m4_data.get("live_face", {})
    anti_spoof = m4_data.get("anti_spoof", {})
    face_match = m4_data.get("face_match", {})

    doc_quality = doc_face.get("quality", "unavailable")
    live_quality = live_face.get("quality", "unavailable")
    both_acceptable = (doc_quality == "acceptable" and live_quality == "acceptable")
    any_quality_poor = (doc_quality == "poor" or live_quality == "poor")

    # Face detection / availability
    if not doc_face.get("detected", False):
        items.append(_item(
            module="M4", signal="face_detection_failed",
            category=EvidenceCategory.BIOMETRIC_CONSISTENCY,
            status=EvidenceStatus.FAIL,
            severity=EvidenceSeverity.MEDIUM,
            confidence=0.95,
            explanation="No face detected on the document image. Biometric matching could not proceed.",
            provenance={**prov_base, "face": "document"},
            correlation_group=CorrelationGroup.BIOMETRIC_QUALITY,
        ))
    if not live_face.get("detected", False):
        items.append(_item(
            module="M4", signal="face_detection_failed",
            category=EvidenceCategory.BIOMETRIC_CONSISTENCY,
            status=EvidenceStatus.FAIL,
            severity=EvidenceSeverity.MEDIUM,
            confidence=0.95,
            explanation="No live face detected in the camera capture. Biometric matching could not proceed.",
            provenance={**prov_base, "face": "live"},
            correlation_group=CorrelationGroup.BIOMETRIC_QUALITY,
        ))

    # Presentation Attack Detection (primary)
    pad_status = anti_spoof.get("status", "pass")
    pad_score = anti_spoof.get("score")
    pad_confidence = float(pad_score) if pad_score is not None else 0.75

    if pad_status == "suspected_spoof":
        items.append(_item(
            module="M4", signal="presentation_attack_detected",
            category=EvidenceCategory.PRESENTATION_ATTACK,
            status=EvidenceStatus.SUSPICIOUS,
            severity=EvidenceSeverity.CRITICAL,
            confidence=pad_confidence,
            explanation=anti_spoof.get("explanation",
                        "Presentation attack suspected. Capture exhibits spoof anomalies."),
            provenance={**prov_base, "pad_model": anti_spoof.get("model", "MiniFASNetV2"),
                        "pad_score": pad_score},
        ))
    elif pad_status == "inconclusive":
        items.append(_item(
            module="M4", signal="pad_inconclusive",
            category=EvidenceCategory.PRESENTATION_ATTACK,
            status=EvidenceStatus.INCONCLUSIVE,
            severity=EvidenceSeverity.LOW,
            confidence=0.60,
            explanation="Presentation attack detection was inconclusive.",
            provenance={**prov_base, "pad_status": pad_status},
        ))

    # Secondary PAD telemetry
    secondary = m4_data.get("secondary_pad", {})
    if secondary:
        secondary_flags = [
            k for k, v in {
                "frequency_domain": secondary.get("frequency_domain", "pass"),
                "texture_analysis": secondary.get("texture_analysis", "pass"),
                "specular_glare":   secondary.get("specular_glare", "pass"),
                "temporal_variance":secondary.get("temporal_variance", "pass"),
            }.items() if v == "suspected_spoof"
        ]
        if secondary_flags:
            items.append(_item(
                module="M4", signal="secondary_pad_anomaly",
                category=EvidenceCategory.PRESENTATION_ATTACK,
                status=EvidenceStatus.SUSPICIOUS,
                severity=EvidenceSeverity.MEDIUM,
                confidence=0.70,
                explanation=f"Secondary optical telemetry anomaly detected: {', '.join(secondary_flags)}.",
                provenance={**prov_base, "flags": secondary_flags},
            ))

    # Face match
    fm_status = face_match.get("status", "unavailable")
    fm_similarity = face_match.get("similarity")
    fm_conf = float(fm_similarity) if fm_similarity is not None else 0.60

    if fm_status == "match":
        # Positive evidence — no contribution
        pass
    elif fm_status == "no_match":
        signal = ("face_mismatch_high_quality" if both_acceptable
                  else "face_mismatch_poor_quality")
        sev = (EvidenceSeverity.HIGH if both_acceptable else EvidenceSeverity.MEDIUM)
        items.append(_item(
            module="M4", signal=signal,
            category=EvidenceCategory.BIOMETRIC_CONSISTENCY,
            status=EvidenceStatus.MISMATCH,
            severity=sev,
            confidence=fm_conf,
            explanation=(
                face_match.get("explanation",
                f"Facial biometric match failed (similarity: {fm_similarity:.2f} "
                f"vs threshold: {face_match.get('threshold', 0.40):.2f}).") +
                ("" if both_acceptable
                 else " Image quality was below preferred threshold; mismatch may be "
                      "influenced by capture conditions.")
            ),
            provenance={**prov_base, "similarity": fm_similarity,
                        "threshold": face_match.get("threshold"),
                        "doc_quality": doc_quality, "live_quality": live_quality},
        ))
    elif fm_status in ("inconclusive", "unavailable"):
        items.append(_item(
            module="M4", signal="face_inconclusive",
            category=EvidenceCategory.BIOMETRIC_CONSISTENCY,
            status=EvidenceStatus.INCONCLUSIVE,
            severity=EvidenceSeverity.LOW,
            confidence=0.70,
            explanation="Biometric face comparison was inconclusive.",
            provenance={**prov_base, "fm_status": fm_status},
        ))

    return items


# ── M5 — Registry ─────────────────────────────────────────────────────────────

# Status values that are provider failures (NOT fraud evidence)
_PROVIDER_FAILURE_STATUSES = {"UNAVAILABLE", "TIMEOUT", "AUTHENTICATION_ERROR", "PROVIDER_ERROR"}

def normalize_registry(m5_data: Optional[Dict[str, Any]]) -> List[RiskEvidenceItem]:
    """
    Normalize Module 5 registry verification results.

    CRITICAL design invariants:
      - Provider failures (TIMEOUT, UNAVAILABLE) are NOT fraud evidence.
        They go to VERIFICATION_UNCERTAINTY, not REGISTRY_STATUS.
      - Development mock results must remain labeled as such.
        Never call them "Government Verified."
      - Registry evidence should be weighted lower when source is 'development_mock'.
      - REVOKED/MISMATCH/SUSPENDED are the strongest evidence items.
      - NOT_FOUND is a meaningful finding but not definitive fraud.
    """
    if not m5_data:
        return [_unavailable("M5", "registry_provider_unavailable",
                             EvidenceCategory.VERIFICATION_UNCERTAINTY,
                             "Module 5 (Registry Verification) did not run.",
                             "registry_engine")]

    items: List[RiskEvidenceItem] = []
    raw_reg = m5_data.get("registry", {})
    if hasattr(raw_reg, "model_dump"):
        registry = raw_reg.model_dump()
    elif hasattr(raw_reg, "dict"):
        registry = raw_reg.dict()
    elif isinstance(raw_reg, dict):
        registry = raw_reg
    else:
        registry = {}

    field_results = m5_data.get("field_results", [])
    raw_meta = m5_data.get("provider_metadata", {})
    if hasattr(raw_meta, "model_dump"):
        provider_meta = raw_meta.model_dump()
    elif hasattr(raw_meta, "dict"):
        provider_meta = raw_meta.dict()
    elif isinstance(raw_meta, dict):
        provider_meta = raw_meta
    else:
        provider_meta = {}

    prov_base = {"source": "registry_engine", "module": "M5",
                 "provider": provider_meta.get("provider_id", "unknown"),
                 "source_type": provider_meta.get("source_type", "unknown")}

    reg_status = registry.get("status", "UNAVAILABLE")
    source_type = provider_meta.get("source_type", "development_mock")

    # Adjust confidence for mock data — it's not a real authoritative source
    mock_confidence_factor = 0.70 if source_type == "development_mock" else 1.0

    # Provider failures → uncertainty, not fraud
    if reg_status in _PROVIDER_FAILURE_STATUSES:
        signal = {
            "UNAVAILABLE":          "registry_provider_unavailable",
            "TIMEOUT":              "module_timeout",
            "AUTHENTICATION_ERROR": "module_error",
            "PROVIDER_ERROR":       "module_error",
        }.get(reg_status, "registry_provider_unavailable")

        items.append(_item(
            module="M5", signal=signal,
            category=EvidenceCategory.VERIFICATION_UNCERTAINTY,
            status=EvidenceStatus(reg_status) if reg_status in EvidenceStatus._value2member_map_ else EvidenceStatus.UNAVAILABLE,
            severity=EvidenceSeverity.LOW,
            confidence=1.0,
            explanation=f"Registry provider was not available ({reg_status}). "
                        "Document could not be checked against the registry.",
            provenance=prov_base,
            available=False,
        ))
        return items

    # Registry statuses → evidence items
    if reg_status == "MATCHED":
        # Positive evidence — no contribution
        pass

    elif reg_status == "REVOKED":
        items.append(_item(
            module="M5", signal="registry_revoked",
            category=EvidenceCategory.REGISTRY_STATUS,
            status=EvidenceStatus.REVOKED,
            severity=EvidenceSeverity.CRITICAL,
            confidence=0.97 * mock_confidence_factor,
            explanation="Registry reports this document as REVOKED. "
                        "The document may have been cancelled or invalidated.",
            provenance=prov_base,
        ))

    elif reg_status == "SUSPENDED":
        items.append(_item(
            module="M5", signal="registry_suspended",
            category=EvidenceCategory.REGISTRY_STATUS,
            status=EvidenceStatus.SUSPENDED,
            severity=EvidenceSeverity.CRITICAL,
            confidence=0.97 * mock_confidence_factor,
            explanation="Registry reports this document as SUSPENDED.",
            provenance=prov_base,
        ))

    elif reg_status == "INVALID":
        items.append(_item(
            module="M5", signal="registry_invalid",
            category=EvidenceCategory.REGISTRY_STATUS,
            status=EvidenceStatus.FAIL,
            severity=EvidenceSeverity.CRITICAL,
            confidence=0.97 * mock_confidence_factor,
            explanation="Registry reports this document as structurally INVALID.",
            provenance=prov_base,
        ))

    elif reg_status == "MISMATCH":
        items.append(_item(
            module="M5", signal="registry_mismatch",
            category=EvidenceCategory.REGISTRY_STATUS,
            status=EvidenceStatus.MISMATCH,
            severity=EvidenceSeverity.HIGH,
            confidence=0.95 * mock_confidence_factor,
            explanation="Registry record found but critical identity fields do not match.",
            provenance=prov_base,
        ))
        # Field-level mismatches (correlated with overall MISMATCH)
        critical_mismatches = [r for r in field_results
                               if r.get("status") == "MISMATCH" and r.get("is_critical")]
        for fld in critical_mismatches[:3]:  # cap at 3 field items
            items.append(_item(
                module="M5", signal="registry_field_mismatch",
                category=EvidenceCategory.REGISTRY_STATUS,
                status=EvidenceStatus.MISMATCH,
                severity=EvidenceSeverity.HIGH,
                confidence=0.95 * mock_confidence_factor,
                explanation=f"Registry field mismatch: '{fld.get('field')}' "
                            f"(document: {fld.get('document_value')}, "
                            f"registry: {fld.get('registry_value')}).",
                provenance={**prov_base, "field": fld.get("field")},
                correlation_group=CorrelationGroup.REGISTRY_FIELD_MISMATCHES,
            ))

    elif reg_status == "EXPIRED":
        items.append(_item(
            module="M5", signal="registry_expired",
            category=EvidenceCategory.REGISTRY_STATUS,
            status=EvidenceStatus.EXPIRED,
            severity=EvidenceSeverity.HIGH,
            confidence=0.97 * mock_confidence_factor,
            explanation="Registry reports this document as EXPIRED.",
            provenance=prov_base,
        ))

    elif reg_status == "NOT_FOUND":
        # NOT_FOUND ≠ forged. The registry may not have records for all valid documents.
        items.append(_item(
            module="M5", signal="registry_not_found",
            category=EvidenceCategory.REGISTRY_STATUS,
            status=EvidenceStatus.NOT_FOUND,
            severity=EvidenceSeverity.MEDIUM,
            confidence=0.80 * mock_confidence_factor,
            explanation="No matching record found in the registry. "
                        "This is not equivalent to a forged document — the registry "
                        "may not hold records for all valid documents.",
            provenance=prov_base,
        ))

    elif reg_status in ("AMBIGUOUS", "INCONCLUSIVE"):
        items.append(_item(
            module="M5", signal="registry_ambiguous",
            category=EvidenceCategory.REGISTRY_STATUS,
            status=EvidenceStatus.INCONCLUSIVE,
            severity=EvidenceSeverity.MEDIUM,
            confidence=0.75 * mock_confidence_factor,
            explanation=f"Registry verification was {reg_status}. "
                        "Officer should perform additional checks.",
            provenance=prov_base,
        ))

    return items


# ── Main entry point ──────────────────────────────────────────────────────────

class RiskNormalizer:
    """
    Converts the M1–M5 session data dict into a flat list of
    canonical RiskEvidenceItems and module availability records.
    """

    def normalize(
        self,
        session_data: Dict[str, Any],
    ) -> tuple[List[RiskEvidenceItem], List[ModuleAvailability]]:
        """
        Normalize all available module data.

        Returns:
            evidence: All RiskEvidenceItem instances.
            availability: ModuleAvailability per module (for completeness reporting).
        """
        all_evidence: List[RiskEvidenceItem] = []
        availability: List[ModuleAvailability] = []

        module_map = [
            ("m1_ocr",        "M1", "OCR Extraction",          normalize_ocr),
            ("m2_validation", "M2", "Document Validation",     normalize_validation),
            ("m3_forensics",  "M3", "Forensic Analysis",       normalize_forensics),
            ("m4_biometrics", "M4", "Biometric Verification",  normalize_biometrics),
            ("m5_registry",   "M5", "Registry Verification",   normalize_registry),
        ]

        for key, module_id, label, fn in module_map:
            raw = session_data.get(key)
            items = fn(raw)
            all_evidence.extend(items)

            if raw is None:
                avail_status = "not_run"
            elif any(not i.available for i in items):
                avail_status = "unavailable" if not any(i.available for i in items) else "partial"
            else:
                avail_status = "completed"

            availability.append(ModuleAvailability(
                module_id=module_id,
                label=label,
                status=avail_status,
                evidence_count=len([i for i in items if i.available]),
            ))

        return all_evidence, availability
