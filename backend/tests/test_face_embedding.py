"""
backend/tests/test_face_embedding.py

Unit tests for FaceEmbeddingEngine.
"""
import numpy as np
from unittest.mock import patch
from app.services.face.face_embedding import FaceEmbeddingEngine


class TestFaceEmbeddingEngine:
    def test_engine_readiness(self):
        engine = FaceEmbeddingEngine()
        assert engine.is_ready() is True

    def test_embedding_is_l2_normalized(self):
        engine = FaceEmbeddingEngine()
        face = np.full((112, 112, 3), 120, dtype=np.uint8)
        emb = engine.generate_embedding(face)

        assert emb is not None
        assert isinstance(emb, np.ndarray)
        assert len(emb.shape) == 1
        # Check L2 unit norm
        norm = np.linalg.norm(emb)
        assert np.isclose(norm, 1.0, atol=1e-4)

    def test_empty_or_none_input(self):
        engine = FaceEmbeddingEngine()
        assert engine.generate_embedding(None) is None
        empty = np.zeros((0, 0, 3), dtype=np.uint8)
        assert engine.generate_embedding(empty) is None

    def test_model_not_ready_returns_none(self):
        engine = FaceEmbeddingEngine()
        with patch.object(engine, "is_ready", return_value=False):
            face = np.full((112, 112, 3), 120, dtype=np.uint8)
            assert engine.generate_embedding(face) is None
