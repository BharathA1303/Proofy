"""
tests/test_risk_normalizer.py

Unit tests for the Module 6 risk normalizer.
Tests every normalization path including full/partial/unavailable inputs.
All tests are deterministic.
"""
from __future__ import annotations

import pytest
from app.services.risk.risk_normalizer import (
    normalize_ocr,
    normalize_validation,
    normalize_forensics,
    normalize_biometrics,
    normalize_registry,
    RiskNormalizer,
)
from app.services.risk.risk_evidence import (
    EvidenceCategory,
    EvidenceSeverity,
    EvidenceStatus,
)


# ── M1 OCR ────────────────────────────────────────────────────────────────────

def test_normalize_ocr_none_returns_unavailable():
    items = normalize_ocr(None)
    assert len(items) == 1
    assert not items[0].available
    assert items[0].module == "M1"


def test_normalize_ocr_completed_clean():
    data = {
        "status": "completed",
        "overall_confidence": 0.95,
        "has_low_confidence_regions": False,
        "mrz_available": True,
        "critical_fields_missing": [],
    }
    items = normalize_ocr(data)
    # No adverse evidence expected
    assert all(i.severity == EvidenceSeverity.NONE or i.status != EvidenceStatus.FAIL
               for i in items)


def test_normalize_ocr_low_confidence_generates_item():
    data = {
        "status": "completed",
        "overall_confidence": 0.45,
        "has_low_confidence_regions": True,
        "mrz_available": True,
        "critical_fields_missing": [],
    }
    items = normalize_ocr(data)
    signals = [i.signal for i in items]
    assert "ocr_low_confidence" in signals
    low_conf = next(i for i in items if i.signal == "ocr_low_confidence")
    assert low_conf.category == EvidenceCategory.VERIFICATION_UNCERTAINTY
    assert low_conf.severity == EvidenceSeverity.MEDIUM


def test_normalize_ocr_mrz_missing_generates_item():
    data = {
        "status": "partial",
        "overall_confidence": 0.80,
        "has_low_confidence_regions": False,
        "mrz_available": False,
        "critical_fields_missing": [],
    }
    items = normalize_ocr(data)
    signals = [i.signal for i in items]
    assert "mrz_unavailable" in signals
    mrz_item = next(i for i in items if i.signal == "mrz_unavailable")
    assert mrz_item.category == EvidenceCategory.DOCUMENT_STRUCTURE
    assert mrz_item.severity == EvidenceSeverity.HIGH


def test_normalize_ocr_failed_returns_error_unavailable():
    data = {"status": "failed", "overall_confidence": 0.0,
            "has_low_confidence_regions": True, "mrz_available": False,
            "critical_fields_missing": []}
    items = normalize_ocr(data)
    assert len(items) == 1
    assert items[0].status == EvidenceStatus.ERROR
    assert not items[0].available


def test_normalize_ocr_critical_fields_missing():
    data = {
        "status": "partial",
        "overall_confidence": 0.85,
        "has_low_confidence_regions": False,
        "mrz_available": True,
        "critical_fields_missing": ["document_number", "date_of_birth"],
    }
    items = normalize_ocr(data)
    field_items = [i for i in items if i.signal == "critical_field_unavailable"]
    assert len(field_items) == 2


# ── M2 Validation ─────────────────────────────────────────────────────────────

def _m2_clean():
    """M2 data with all checks passing."""
    return {
        "status": "passed",
        "summary": "All checks passed.",
        "checks": {
            "mrz_structure": {"valid": True, "status": "passed", "message": "OK"},
            "document_number_checksum": {"valid": True, "status": "passed", "computed": 5, "actual": 5, "message": "OK"},
            "dob_checksum": {"valid": True, "status": "passed", "computed": 3, "actual": 3, "message": "OK"},
            "expiry_checksum": {"valid": True, "status": "passed", "computed": 7, "actual": 7, "message": "OK"},
            "composite_checksum": {"valid": True, "status": "passed", "computed": 2, "actual": 2, "message": "OK"},
            "expiry_date": {"valid": True, "status": "passed", "expired": False, "expiry_date": "2030-01-01", "message": "OK"},
            "passport_number_binding": {"valid": True, "status": "passed", "match": True, "viz_value": "AB123456", "mrz_value": "AB123456", "message": "OK"},
            "viz_mrz_consistency": {"valid": True, "status": "passed", "fields": {}, "message": "OK"},
        }
    }


def test_normalize_validation_none():
    items = normalize_validation(None)
    assert len(items) == 1
    assert not items[0].available


def test_normalize_validation_all_pass():
    items = normalize_validation(_m2_clean())
    # No adverse items
    adverse = [i for i in items if i.severity != EvidenceSeverity.NONE and i.available]
    assert len(adverse) == 0


def test_normalize_validation_checksum_fail():
    data = _m2_clean()
    data["checks"]["document_number_checksum"] = {
        "valid": False, "status": "failed", "computed": 9, "actual": 5,
        "message": "Mismatch."
    }
    items = normalize_validation(data)
    signals = [i.signal for i in items if i.available]
    assert "document_number_checksum_fail" in signals
    item = next(i for i in items if i.signal == "document_number_checksum_fail")
    assert item.severity == EvidenceSeverity.HIGH
    assert item.category == EvidenceCategory.DOCUMENT_INTEGRITY


def test_normalize_validation_binding_trap_fail():
    data = _m2_clean()
    data["checks"]["passport_number_binding"] = {
        "valid": False, "status": "failed", "match": False,
        "viz_value": "AB123456", "mrz_value": "XX999999", "message": "Mismatch."
    }
    items = normalize_validation(data)
    signals = [i.signal for i in items]
    assert "document_number_binding_mismatch" in signals
    item = next(i for i in items if i.signal == "document_number_binding_mismatch")
    assert item.severity == EvidenceSeverity.CRITICAL


def test_normalize_validation_expired():
    data = _m2_clean()
    data["checks"]["expiry_date"] = {
        "valid": False, "status": "failed", "expired": True,
        "expiry_date": "2020-01-01", "message": "Expired."
    }
    items = normalize_validation(data)
    expired = [i for i in items if i.signal == "document_expired"]
    assert len(expired) == 1
    assert expired[0].status == EvidenceStatus.EXPIRED


def test_normalize_validation_viz_mrz_mismatch():
    data = _m2_clean()
    data["checks"]["viz_mrz_consistency"] = {
        "valid": False, "status": "failed",
        "fields": {
            "document_number": {"viz": "AB123456", "mrz": "AB999999", "match": False,
                                "status": "mismatch", "message": "Mismatch."},
        },
        "message": "Field mismatch."
    }
    items = normalize_validation(data)
    signals = [i.signal for i in items]
    assert "viz_mrz_document_number_mismatch" in signals


# ── M3 Forensics ──────────────────────────────────────────────────────────────

def test_normalize_forensics_none():
    items = normalize_forensics(None)
    assert not items[0].available


def test_normalize_forensics_no_anomaly():
    data = {
        "status": "completed",
        "overall_assessment": "no_significant_anomaly",
        "signals": [
            {"type": "ela", "status": "normal", "severity": "low", "confidence": 0.9, "description": "Normal."},
        ]
    }
    items = normalize_forensics(data)
    adverse = [i for i in items if i.available and i.severity != EvidenceSeverity.NONE]
    assert len(adverse) == 0


def test_normalize_forensics_ela_suspicious():
    data = {
        "status": "completed",
        "overall_assessment": "suspicious",
        "signals": [
            {"type": "ela", "status": "suspicious", "severity": "high", "confidence": 0.82, "description": "ELA anomaly detected."},
        ]
    }
    items = normalize_forensics(data)
    ela = [i for i in items if i.signal == "forensic_ela_anomaly"]
    assert len(ela) == 1
    assert ela[0].severity == EvidenceSeverity.HIGH
    # Should be in correlation group
    assert ela[0].correlation_group is not None


def test_normalize_forensics_high_concern_overall():
    data = {
        "status": "completed",
        "overall_assessment": "high_forensic_concern",
        "signals": [
            {"type": "ela", "status": "suspicious", "severity": "high", "confidence": 0.9, "description": "ELA."},
            {"type": "compression", "status": "suspicious", "severity": "medium", "confidence": 0.75, "description": "Compression."},
        ]
    }
    items = normalize_forensics(data)
    signals = [i.signal for i in items]
    assert "forensic_high_concern" in signals


def test_normalize_forensics_insufficient_data():
    data = {"status": "insufficient_data", "overall_assessment": "insufficient_data", "signals": []}
    items = normalize_forensics(data)
    assert len(items) == 1
    assert not items[0].available


# ── M4 Biometrics ─────────────────────────────────────────────────────────────

def _m4_clean():
    return {
        "overall_assessment": "FACE_MATCH",
        "document_face": {"detected": True, "quality": "acceptable"},
        "live_face": {"detected": True, "quality": "acceptable"},
        "anti_spoof": {"status": "pass", "score": 0.95, "model": "MiniFASNetV2", "explanation": "Live."},
        "secondary_pad": {"frequency_domain": "pass", "texture_analysis": "pass",
                         "specular_glare": "pass", "temporal_variance": "pass"},
        "face_match": {"status": "match", "similarity": 0.78, "threshold": 0.40,
                       "explanation": "Match confirmed."},
    }


def test_normalize_biometrics_none():
    items = normalize_biometrics(None)
    assert not items[0].available


def test_normalize_biometrics_clean():
    items = normalize_biometrics(_m4_clean())
    adverse = [i for i in items if i.available and i.severity != EvidenceSeverity.NONE]
    assert len(adverse) == 0


def test_normalize_biometrics_face_mismatch_good_quality():
    data = _m4_clean()
    data["face_match"]["status"] = "no_match"
    data["face_match"]["similarity"] = 0.25
    items = normalize_biometrics(data)
    mismatch = [i for i in items if "face_mismatch" in i.signal]
    assert len(mismatch) > 0
    assert mismatch[0].signal == "face_mismatch_high_quality"
    assert mismatch[0].severity == EvidenceSeverity.HIGH


def test_normalize_biometrics_face_mismatch_poor_quality():
    data = _m4_clean()
    data["face_match"]["status"] = "no_match"
    data["live_face"]["quality"] = "poor"
    items = normalize_biometrics(data)
    mismatch = [i for i in items if "face_mismatch" in i.signal]
    assert mismatch[0].signal == "face_mismatch_poor_quality"
    assert mismatch[0].severity == EvidenceSeverity.MEDIUM


def test_normalize_biometrics_presentation_attack():
    data = _m4_clean()
    data["anti_spoof"]["status"] = "suspected_spoof"
    data["anti_spoof"]["score"] = 0.22
    items = normalize_biometrics(data)
    pad = [i for i in items if i.signal == "presentation_attack_detected"]
    assert len(pad) == 1
    assert pad[0].severity == EvidenceSeverity.CRITICAL


def test_normalize_biometrics_no_face_detected():
    data = _m4_clean()
    data["document_face"]["detected"] = False
    items = normalize_biometrics(data)
    detect = [i for i in items if i.signal == "face_detection_failed"]
    assert len(detect) > 0


# ── M5 Registry ───────────────────────────────────────────────────────────────

def _m5(status: str):
    return {
        "registry": {"status": status, "record_found": status == "MATCHED"},
        "field_results": [],
        "provider_metadata": {"provider_id": "mock_passport", "source_type": "development_mock"},
    }


def test_normalize_registry_none():
    items = normalize_registry(None)
    assert not items[0].available


def test_normalize_registry_matched():
    items = normalize_registry(_m5("MATCHED"))
    adverse = [i for i in items if i.available and i.severity != EvidenceSeverity.NONE]
    assert len(adverse) == 0


def test_normalize_registry_revoked():
    items = normalize_registry(_m5("REVOKED"))
    revoked = [i for i in items if i.signal == "registry_revoked"]
    assert len(revoked) == 1
    assert revoked[0].severity == EvidenceSeverity.CRITICAL


def test_normalize_registry_not_found_medium_severity():
    items = normalize_registry(_m5("NOT_FOUND"))
    nf = [i for i in items if i.signal == "registry_not_found"]
    assert len(nf) == 1
    # NOT_FOUND is NOT critical
    assert nf[0].severity == EvidenceSeverity.MEDIUM


def test_normalize_registry_provider_failure_goes_to_uncertainty():
    for status in ("UNAVAILABLE", "TIMEOUT", "PROVIDER_ERROR"):
        items = normalize_registry(_m5(status))
        assert all(i.category == EvidenceCategory.VERIFICATION_UNCERTAINTY for i in items)
        assert all(not i.available for i in items)


def test_normalize_registry_mismatch_with_field_results():
    data = {
        "registry": {"status": "MISMATCH", "record_found": True},
        "field_results": [
            {"field": "document_number", "document_value": "AB123", "registry_value": "AB999",
             "status": "MISMATCH", "is_critical": True},
            {"field": "name", "document_value": "JOHN", "registry_value": "JOHN",
             "status": "MATCH", "is_critical": False},
        ],
        "provider_metadata": {"provider_id": "mock_passport", "source_type": "development_mock"},
    }
    items = normalize_registry(data)
    mismatch = [i for i in items if i.signal == "registry_mismatch"]
    field_mismatch = [i for i in items if i.signal == "registry_field_mismatch"]
    assert len(mismatch) == 1
    assert len(field_mismatch) == 1  # Only critical mismatches


# ── Full normalizer ───────────────────────────────────────────────────────────

def test_risk_normalizer_full_clean():
    session = {
        "m1_ocr": {
            "status": "completed", "overall_confidence": 0.95,
            "has_low_confidence_regions": False, "mrz_available": True,
            "critical_fields_missing": [],
        },
        "m2_validation": {
            "status": "passed", "summary": "All passed.",
            "checks": {
                "mrz_structure": {"valid": True, "status": "passed", "message": "OK"},
                "document_number_checksum": {"valid": True, "status": "passed", "computed": 5, "actual": 5, "message": "OK"},
                "dob_checksum": {"valid": True, "status": "passed", "computed": 3, "actual": 3, "message": "OK"},
                "expiry_checksum": {"valid": True, "status": "passed", "computed": 7, "actual": 7, "message": "OK"},
                "composite_checksum": {"valid": True, "status": "passed", "computed": 2, "actual": 2, "message": "OK"},
                "expiry_date": {"valid": True, "status": "passed", "expired": False, "expiry_date": "2030-01-01", "message": "OK"},
                "passport_number_binding": {"valid": True, "status": "passed", "match": True, "viz_value": "A", "mrz_value": "A", "message": "OK"},
                "viz_mrz_consistency": {"valid": True, "status": "passed", "fields": {}, "message": "OK"},
            }
        },
        "m3_forensics": {
            "status": "completed", "overall_assessment": "no_significant_anomaly", "signals": []
        },
        "m4_biometrics": {
            "overall_assessment": "FACE_MATCH",
            "document_face": {"detected": True, "quality": "acceptable"},
            "live_face": {"detected": True, "quality": "acceptable"},
            "anti_spoof": {"status": "pass", "score": 0.95, "model": "MiniFASNetV2", "explanation": "Live."},
            "secondary_pad": {"frequency_domain": "pass", "texture_analysis": "pass",
                             "specular_glare": "pass", "temporal_variance": "pass"},
            "face_match": {"status": "match", "similarity": 0.80, "threshold": 0.40, "explanation": "Match."},
        },
        "m5_registry": {
            "registry": {"status": "MATCHED", "record_found": True},
            "field_results": [],
            "provider_metadata": {"provider_id": "mock_passport", "source_type": "development_mock"},
        },
    }
    normalizer = RiskNormalizer()
    evidence, availability = normalizer.normalize(session)
    assert len(availability) == 5
    all_completed = all(a.status == "completed" for a in availability)
    assert all_completed
    # Clean session: no HIGH/CRITICAL items
    adverse = [e for e in evidence if e.available and e.severity.value in ("HIGH", "CRITICAL")]
    assert len(adverse) == 0


def test_risk_normalizer_all_modules_absent():
    normalizer = RiskNormalizer()
    evidence, availability = normalizer.normalize({})
    assert len(availability) == 5
    assert all(a.status == "not_run" for a in availability)
    # All evidence items should be unavailable
    assert all(not e.available for e in evidence)
