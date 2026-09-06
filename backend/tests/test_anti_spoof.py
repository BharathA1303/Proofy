"""
backend/tests/test_anti_spoof.py

Unit tests for Anti-Spoofing & Presentation Attack Detection.
"""
import numpy as np
import cv2
from app.services.face.anti_spoof import anti_spoof_engine


def _create_natural_face(w=160, h=180):
    """Generate a clean synthetic face crop with natural skin chrominance (YCrCb)."""
    # Create natural skin tones: Y ~ 140, Cr ~ 150, Cb ~ 110
    ycrcb = np.zeros((h, w, 3), dtype=np.uint8)
    ycrcb[:, :, 0] = 140
    ycrcb[:, :, 1] = 150
    ycrcb[:, :, 2] = 110
    bgr = cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)

    # Add soft features (gradient)
    color = (int(bgr[0, 0, 0] * 0.9), int(bgr[0, 0, 1] * 0.9), int(bgr[0, 0, 2] * 0.9))
    cv2.circle(bgr, (w // 2, h // 2), 40, color, -1)
    bgr = cv2.GaussianBlur(bgr, (5, 5), 0)

    return bgr


class TestAntiSpoof:
    def test_genuine_face_passes(self):
        face = _create_natural_face()
        res = anti_spoof_engine.analyze_presentation(face)
        assert res.status == "pass"
        assert res.is_pass is True
        assert res.score is not None
        assert res.score >= 0.65

    def test_specular_glare_attack_suspected(self):
        # Digital screen / glass reflection produces localized bright glare spots
        face = _create_natural_face()
        h, w = face.shape[:2]
        # Introduce bright specular glare spot (V > 240, S < 30)
        face[20:60, 20:60] = [255, 255, 255]

        res = anti_spoof_engine.analyze_presentation(face)
        # Specular anomaly should penalize score or trigger suspected spoof
        assert res.score is not None
        assert res.score < 0.85
        assert "specular_glare_ratio" in res.signals

    def test_high_frequency_moire_attack_suspected(self):
        # Digital screen pixel grid produces high-frequency grid pattern
        face = _create_natural_face()
        h, w = face.shape[:2]
        # Add high frequency periodic checkerboard
        for y in range(0, h, 2):
            for x in range(0, w, 2):
                face[y, x] = [255, 0, 0]

        res = anti_spoof_engine.analyze_presentation(face)
        assert res.signals["high_frequency_ratio"] > 0.50

    def test_identical_multi_frame_static_spoof(self):
        # Static printed photo placed in front of camera: 0 motion across frames
        face = _create_natural_face()
        # Pass identical frames
        sequence = [face.copy(), face.copy(), face.copy()]
        res = anti_spoof_engine.analyze_presentation(face, sequence_crops=sequence)
        assert res.signals["temporal_variance"] is not None
        assert res.signals["temporal_variance"] < 0.15

    def test_empty_image_returns_model_unavailable(self):
        res = anti_spoof_engine.analyze_presentation(None)
        assert res.status == "model_unavailable"
        assert res.score is None
