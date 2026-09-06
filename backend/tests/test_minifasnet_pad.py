"""
backend/tests/test_minifasnet_pad.py

Unit tests for MiniFASNetPAD Presentation Attack Detection.
Tests model initialization, single-frame inference, and multi-frame temporal aggregation.
"""
import numpy as np
import pytest

from app.services.face.minifasnet_pad import MiniFASNetPAD


class TestMiniFASNetPAD:
    def test_model_initialization(self):
        pad = MiniFASNetPAD()
        assert pad.is_available() is True
        info = pad.model_info()
        assert info["model_name"] == "MiniFASNetV2"
        assert info["available"] is True
        assert info["input_size"] == [80, 80]

    def test_single_frame_predict(self):
        pad = MiniFASNetPAD()
        crop = np.full((120, 120, 3), 150, dtype=np.uint8)
        bbox = (10, 10, 100, 100)
        orig = np.full((200, 200, 3), 150, dtype=np.uint8)

        res = pad.predict(crop, bbox=bbox, original_img=orig)
        assert res.model_name == "MiniFASNetV2"
        assert res.status in ("pass", "suspected_spoof", "inconclusive")
        assert res.score is not None
        assert 0.0 <= res.score <= 1.0
        assert "p_genuine" in res.details
        assert "p_spoof" in res.details

    def test_sequence_frames_predict(self):
        pad = MiniFASNetPAD()
        orig = np.full((200, 200, 3), 150, dtype=np.uint8)
        crop1 = np.full((100, 100, 3), 150, dtype=np.uint8)
        crop2 = np.full((100, 100, 3), 152, dtype=np.uint8)
        crop3 = np.full((100, 100, 3), 148, dtype=np.uint8)

        sequence_items = [
            (crop1, (10, 10, 80, 80), orig),
            (crop2, (10, 10, 80, 80), orig),
            (crop3, (10, 10, 80, 80), orig),
        ]

        res = pad.predict_sequence(sequence_items)
        assert res.model_name == "MiniFASNetV2"
        assert res.status in ("pass", "suspected_spoof", "inconclusive")
        assert res.score is not None
        assert res.details.get("burst_frame_count") == 3

    def test_empty_or_none_input(self):
        pad = MiniFASNetPAD()
        res = pad.predict(None)
        assert res.status == "inconclusive"
        assert res.score is None
