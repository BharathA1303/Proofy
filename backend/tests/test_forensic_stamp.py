"""
backend/tests/test_forensic_stamp.py

Unit tests for Module 3 Stamp & Consular Seal Forgery Detection.
"""
import numpy as np
import cv2
import pytest

from app.services.forensics.stamp_analysis import analyze_document_stamps


def test_smart_cards_not_applicable():
    """National ID and Driving Licence smart cards should not require wet-ink stamps."""
    img = np.ones((400, 600, 3), dtype=np.uint8) * 240
    res_dl = analyze_document_stamps(img, document_type="driving_license")
    assert res_dl.status == "normal"
    assert res_dl.stamp_detected is False
    assert res_dl.metrics.get("applicable") is False

    res_nid = analyze_document_stamps(img, document_type="national_id")
    assert res_nid.status == "normal"
    assert res_nid.stamp_detected is False


def test_clean_passport_stamp_inspection():
    """Passport without anomalous marks passes cleanly."""
    img = np.ones((800, 600, 3), dtype=np.uint8) * 245
    res = analyze_document_stamps(img, document_type="passport")
    assert res.status == "normal"
    assert res.severity == "low"
    assert len(res.indicators) == 0


def test_authentic_looking_stamp():
    """Simulate a stamp with realistic physical ink variance."""
    img = np.ones((800, 600, 3), dtype=np.uint8) * 245
    # Draw a simulated violet immigration stamp with texture noise
    cv2.circle(img, (300, 400), 70, (140, 50, 130), 4)
    # Add random ink variance
    noise = np.random.normal(0, 15, img.shape).astype(np.int16)
    noisy_img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    res = analyze_document_stamps(noisy_img, document_type="passport")
    assert res.status == "normal"
    assert res.severity == "low"
    assert len(res.indicators) == 0
