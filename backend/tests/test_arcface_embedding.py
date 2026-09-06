"""
backend/tests/test_arcface_embedding.py

Unit tests for ArcFaceEmbeddingModel.
Tests model initialization, embedding dimensionality (512), L2 normalization, and inference.
"""
import numpy as np
import pytest

from app.services.face.arcface_embedding import ArcFaceEmbeddingModel


class TestArcFaceEmbedding:
    def test_model_initialization_and_availability(self):
        model = ArcFaceEmbeddingModel()
        assert model.is_available() is True
        assert model.get_embedding_dimension() == 512
        info = model.model_info()
        assert info["model_name"] == "ArcFace-w600k_r50"
        assert info["embedding_dimension"] == 512

    def test_embedding_output_dimension_and_normalization(self):
        model = ArcFaceEmbeddingModel()
        # Synthetic aligned 112x112 facial crop
        crop = np.full((112, 112, 3), 120, dtype=np.uint8)
        crop[30:50, 30:50] = 50
        crop[30:50, 62:82] = 50

        emb = model.get_embedding(crop)
        assert emb.shape == (512,)
        assert emb.dtype == np.float32

        # L2 norm must equal 1.0 within numerical precision
        norm = np.linalg.norm(emb)
        assert abs(norm - 1.0) < 1e-4

    def test_identical_input_produces_identical_embedding(self):
        model = ArcFaceEmbeddingModel()
        crop = np.random.randint(0, 255, (112, 112, 3), dtype=np.uint8)

        emb1 = model.get_embedding(crop)
        emb2 = model.get_embedding(crop)

        cos_sim = float(np.dot(emb1, emb2))
        assert abs(cos_sim - 1.0) < 1e-5

    def test_invalid_input_handling(self):
        model = ArcFaceEmbeddingModel()
        with pytest.raises(ValueError):
            model.get_embedding(None)

        with pytest.raises(ValueError):
            model.get_embedding(np.zeros((0, 0, 3), dtype=np.uint8))
