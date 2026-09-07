"""
backend/app/services/face/arcface_embedding.py

ArcFace face embedding extraction engine powered by ONNX Runtime.
Architecture: InsightFace ResNet-50 trained with Additive Angular Margin Loss (ArcFace).
Model: w600k_r50.onnx (WebFace600K dataset).

Output: 512-dimensional L2-normalized Euclidean unit vector.

Privacy & Security Architecture:
  - Initialized once on application startup and reused across requests.
  - NEVER logs raw feature vectors or embeddings.
  - NEVER returns raw embeddings over the network or saves them to disk.
  - Embeddings exist solely in transient volatile memory for cosine comparison.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import cv2
import numpy as np

from app.core.config import settings
from app.services.face.embedding_interface import FaceEmbeddingModel

logger = logging.getLogger(__name__)


class ArcFaceEmbeddingModel(FaceEmbeddingModel):
    """
    ArcFace deep feature representation engine.
    Extracts 512-dimensional unit-normalized embeddings from 112x112 aligned face crops.
    """

    def __init__(self, model_path: Optional[str] = None) -> None:
        self._model_path = model_path or settings.ARCFACE_MODEL_PATH
        self._session = None
        self._input_name = "input.1"
        self._initialized = False
        self.initialize()

    def initialize(self) -> None:
        """Initialize ONNX Runtime inference session with ArcFace weights."""
        if not self._model_path or not os.path.exists(self._model_path):
            logger.warning(
                "ArcFace model file not found at '%s'. Embedding engine will report MODEL_UNAVAILABLE.",
                self._model_path,
            )
            self._initialized = False
            return

        try:
            import onnxruntime as ort

            logger.info("Initializing ArcFace ONNX inference session from '%s'...", self._model_path)
            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 2
            opts.intra_op_num_threads = 2
            self._session = ort.InferenceSession(
                self._model_path,
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
            inputs = self._session.get_inputs()
            if inputs:
                self._input_name = inputs[0].name

            self._initialized = True
            logger.info("ArcFace embedding engine initialized successfully (input_name=%s).", self._input_name)
        except Exception as exc:
            logger.error("Failed to initialize ArcFace ONNX model: %s", exc, exc_info=True)
            self._session = None
            self._initialized = False

    def is_available(self) -> bool:
        return self._initialized and self._session is not None

    def get_embedding_dimension(self) -> int:
        return 512

    def model_info(self) -> Dict[str, Any]:
        return {
            "model_name": "ArcFace-w600k_r50",
            "backend": "ONNXRuntime-CPU",
            "embedding_dimension": 512,
            "input_size": [112, 112],
            "available": self.is_available(),
        }

    def _infer_single(self, face_bgr: np.ndarray) -> np.ndarray:
        """Run single forward inference pass on 112x112 BGR face."""
        if face_bgr.shape[:2] != (112, 112):
            face_bgr = cv2.resize(face_bgr, (112, 112), interpolation=cv2.INTER_LANCZOS4)

        rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
        blob = (rgb.astype(np.float32) - 127.5) / 128.0
        tensor = blob.transpose(2, 0, 1)[np.newaxis, ...]

        outputs = self._session.run(None, {self._input_name: tensor})
        raw_feat = outputs[0].flatten().astype(np.float32)
        norm = float(np.linalg.norm(raw_feat))
        return (raw_feat / max(norm, 1e-10)).astype(np.float32)

    def get_embedding(self, aligned_face: np.ndarray, use_tta: bool = True) -> np.ndarray:
        """
        Extract a 512-dimensional L2-normalized ArcFace embedding vector.
        Supports InsightFace Test-Time Augmentation (TTA) via horizontal flipping,
        canceling out lateral illumination imbalances and head tilt biases.

        Args:
            aligned_face: 112x112 BGR facial crop, geometrically aligned.
            use_tta: If True, aggregates embeddings from original and mirrored faces.

        Returns:
            1D float32 NumPy array of shape (512,) where L2 norm equals 1.0.

        Raises:
            RuntimeError if model is unavailable or input is invalid.
        """
        if not self.is_available():
            raise RuntimeError("ArcFace model is unavailable. Ensure w600k_r50.onnx is loaded.")

        if aligned_face is None or aligned_face.size == 0:
            raise ValueError("Invalid facial crop provided to ArcFace embedding model.")

        feat_orig = self._infer_single(aligned_face)
        if not use_tta:
            return feat_orig

        # Test-Time Augmentation (TTA): average original and horizontally flipped feature vectors
        flipped = cv2.flip(aligned_face, 1)
        feat_flip = self._infer_single(flipped)

        combined = feat_orig + feat_flip
        norm = float(np.linalg.norm(combined))
        return (combined / max(norm, 1e-10)).astype(np.float32)
