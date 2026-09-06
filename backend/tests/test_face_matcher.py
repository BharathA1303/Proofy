"""
backend/tests/test_face_matcher.py

Unit tests for face embedding matching and configurable threshold behavior.
"""
import numpy as np
import pytest
from app.services.face.face_matcher import compare_face_embeddings
from app.core.config import settings


class TestFaceMatcher:
    def test_exact_match_above_threshold(self):
        # Identical unit vectors
        v = np.random.randn(512).astype(np.float32)
        v = v / np.linalg.norm(v)

        result = compare_face_embeddings(v, v, threshold=0.50)
        assert result.status == "match"
        assert result.is_match is True
        assert pytest.approx(result.similarity, rel=1e-3) == 1.0
        assert result.threshold == 0.50

    def test_mismatch_below_threshold(self):
        # Orthogonal vectors -> cosine similarity == 0.0
        v1 = np.zeros(512, dtype=np.float32)
        v1[0] = 1.0
        v2 = np.zeros(512, dtype=np.float32)
        v2[1] = 1.0

        result = compare_face_embeddings(v1, v2, threshold=0.50)
        assert result.status == "no_match"
        assert result.is_match is False
        assert pytest.approx(result.similarity, abs=1e-3) == 0.0

    def test_exact_threshold_behavior(self):
        # When similarity exactly equals threshold, it must be classified as MATCH
        v1 = np.array([1.0, 0.0], dtype=np.float32)
        # Cosine of 60 degrees = 0.50
        v2 = np.array([0.5, np.sqrt(0.75)], dtype=np.float32)

        result = compare_face_embeddings(v1, v2, threshold=0.50)
        assert result.status == "match"
        assert pytest.approx(result.similarity, abs=1e-3) == 0.50

    def test_borderline_inconclusive_behavior(self):
        # When similarity is just below threshold (e.g. within 0.03 margin)
        v1 = np.array([1.0, 0.0], dtype=np.float32)
        # Angle with cos ~ 0.48
        angle = np.arccos(0.48)
        v2 = np.array([np.cos(angle), np.sin(angle)], dtype=np.float32)

        result = compare_face_embeddings(v1, v2, threshold=0.50)
        assert result.status == "inconclusive"
        assert result.is_match is False

    def test_none_embedding_returns_unavailable(self):
        v = np.random.randn(512).astype(np.float32)
        result = compare_face_embeddings(v, None, threshold=0.50)
        assert result.status == "unavailable"
        assert result.similarity is None

        result2 = compare_face_embeddings(None, None, threshold=0.50)
        assert result2.status == "unavailable"
        assert result2.similarity is None

    def test_zero_vector_returns_unavailable(self):
        zero = np.zeros(512, dtype=np.float32)
        v = np.random.randn(512).astype(np.float32)
        v = v / np.linalg.norm(v)

        result = compare_face_embeddings(zero, v, threshold=0.50)
        assert result.status == "unavailable"
        assert result.similarity is None
