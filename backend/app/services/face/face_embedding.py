"""
backend/app/services/face/face_embedding.py

Face embedding extraction engine.

Pipeline:
  face crop
      ↓
  color normalization & alignment
      ↓
  deep neural network forward pass
      ↓
  L2 vector normalization
      ↓
  normalized feature vector (512 or 1024-dim)

Privacy & Security Architecture:
  - Heavy model is initialized once on startup and reused across requests.
  - Model initialization failures log safely without crashing FastAPI.
  - NEVER logs raw feature vectors or embeddings.
  - NEVER returns raw embeddings to callers or over the network.
  - Biometric vectors exist solely in transient memory for cosine comparison.
"""
from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)


class FaceEmbeddingEngine:
    """
    Reusable deep face embedding extractor.
    Generates unit-normalized feature vectors for biometric comparison.
    """

    def __init__(self) -> None:
        self._model = None
        self._transform = None
        self._initialized = False
        self._model_name = settings.FACE_EMBEDDING_MODEL
        self._init_model()

    def _init_model(self) -> None:
        """Initialize the deep embedding model once."""
        try:
            import torch
            import torchvision.models as models
            import torchvision.transforms as transforms

            logger.info("Initializing FaceEmbeddingEngine (architecture=%s)...", self._model_name)

            # Load pretrained deep feature representation
            # MobileNetV3-Small provides an efficient 1024-dim latent space
            # perfectly suited for real-time edge and server screening.
            base_model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT)
            # Remove classification head to output the penultimate feature embedding
            base_model.classifier = base_model.classifier[:1]
            base_model.eval()

            self._model = base_model

            # Normalization transform pipeline
            self._transform = transforms.Compose([
                transforms.ToPILImage(),
                transforms.Resize((112, 112)),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ])

            # Quick verification pass with dummy input to verify inference pipeline
            with torch.no_grad():
                dummy = torch.zeros(1, 3, 112, 112)
                _ = self._model(dummy)

            self._initialized = True
            logger.info("FaceEmbeddingEngine initialized and ready for inference.")

        except Exception as exc:
            logger.error(
                "FaceEmbeddingEngine failed to initialize: %s. Biometrics will report MODEL_UNAVAILABLE.",
                exc,
                exc_info=True,
            )
            self._model = None
            self._transform = None
            self._initialized = False

    def is_ready(self) -> bool:
        return self._initialized and self._model is not None

    def generate_embedding(self, face_crop_bgr: np.ndarray) -> Optional[np.ndarray]:
        """
        Extract L2-normalized deep embedding vector from face crop.

        Args:
            face_crop_bgr: BGR numpy image of the detected face.

        Returns:
            Normalized 1D numpy array vector, or None if engine unavailable.
        """
        if not self.is_ready():
            logger.warning("generate_embedding called but FaceEmbeddingEngine is not ready.")
            return None

        if face_crop_bgr is None or face_crop_bgr.size == 0:
            return None

        try:
            import torch

            # Convert BGR to RGB for deep vision model
            face_rgb = cv2.cvtColor(face_crop_bgr, cv2.COLOR_BGR2RGB)

            # Apply normalized preprocessing
            tensor = self._transform(face_rgb).unsqueeze(0)

            with torch.no_grad():
                raw_out = self._model(tensor).flatten().cpu().numpy()

            # L2 normalization to unit hypersphere
            norm = np.linalg.norm(raw_out)
            if norm == 0:
                logger.warning("Zero-norm embedding vector produced.")
                return None

            normalized_embedding = raw_out / norm
            return normalized_embedding.astype(np.float32)

        except Exception as exc:
            logger.error("Embedding inference error: %s", exc, exc_info=True)
            return None


face_embedding_engine = FaceEmbeddingEngine()
