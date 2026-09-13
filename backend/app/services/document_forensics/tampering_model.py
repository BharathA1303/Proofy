"""
backend/app/services/document_forensics/tampering_model.py

AI Document Tampering Deep-Learning Model Interface.
Strictly adheres to the Model Availability Contract:
  - If trained model weights are absent: returns MODEL_UNAVAILABLE (no fake confidence).
  - If inference fails: returns MODEL_INFERENCE_FAILED.
  - If weights are available: executes genuine tensor inference.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.services.document_forensics.schema import (
    AIModelForensicResult,
    ForensicFinding,
    ModelStatus,
    SignalSeverity,
    SignalStatus,
    SignalType,
)

logger = logging.getLogger(__name__)


class DocumentTamperingModel:
    """
    Deep-learning tampering localization & classification interface.
    Follows strict no-fabrication contract: never outputs synthetic confidence.
    """

    def __init__(self, weights_path: Optional[str] = None) -> None:
        self.weights_path = weights_path
        self.status = ModelStatus.MODEL_UNAVAILABLE
        self._model = None
        self._initialize_model()

    def _initialize_model(self) -> None:
        """Attempt to load trained neural network weights if path is provided."""
        if not self.weights_path:
            self.status = ModelStatus.MODEL_UNAVAILABLE
            return

        p = Path(self.weights_path)
        if not p.exists() or not p.is_file():
            logger.info("DocumentTamperingModel: weights file not found at '%s'. Setting MODEL_UNAVAILABLE.", self.weights_path)
            self.status = ModelStatus.MODEL_UNAVAILABLE
            return

        try:
            # Check for ONNX runtime
            if p.suffix.lower() == ".onnx":
                import onnxruntime as ort
                self._model = ort.InferenceSession(str(p), providers=["CPUExecutionProvider"])
                self.status = ModelStatus.MODEL_AVAILABLE
                logger.info("DocumentTamperingModel: ONNX model loaded successfully from %s", p)
            elif p.suffix.lower() in (".pt", ".pth"):
                import torch
                self._model = torch.load(str(p), map_location="cpu")
                if hasattr(self._model, "eval"):
                    self._model.eval()
                self.status = ModelStatus.MODEL_AVAILABLE
                logger.info("DocumentTamperingModel: PyTorch model loaded successfully from %s", p)
            else:
                self.status = ModelStatus.MODEL_UNAVAILABLE
                logger.warning("DocumentTamperingModel: unsupported model extension '%s'", p.suffix)
        except Exception as exc:
            logger.warning("DocumentTamperingModel: failed to load weights at '%s': %s", self.weights_path, exc)
            self.status = ModelStatus.MODEL_UNAVAILABLE

    def predict(self, image_np_bgr: np.ndarray) -> Tuple[AIModelForensicResult, Optional[ForensicFinding]]:
        """
        Execute deep-learning tampering inference if model is available.

        Returns:
            Tuple of (AIModelForensicResult, Optional[ForensicFinding])
        """
        if self.status != ModelStatus.MODEL_AVAILABLE or self._model is None:
            res = AIModelForensicResult(
                status=ModelStatus.MODEL_UNAVAILABLE,
                model_name="Generic_Tampering_Detector",
                version="1.0.0",
                weights_path=self.weights_path,
                confidence=None,
                tampering_detected=None,
                explanation="Model weights not present. System running in classical forensic mode.",
            )
            return res, None

        # Execute genuine model inference
        try:
            h, w = image_np_bgr.shape[:2]
            # Standard input preprocessing: resize to 256x256, normalize to [0, 1]
            resized = cv2.resize(image_np_bgr, (256, 256))
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            tensor_chw = np.transpose(rgb, (2, 0, 1))
            batch_input = np.expand_dims(tensor_chw, axis=0)

            if isinstance(self._model, ort.InferenceSession):
                input_name = self._model.get_inputs()[0].name
                outputs = self._model.run(None, {input_name: batch_input})
                raw_pred = float(outputs[0].flatten()[0])
            else:
                # PyTorch model
                import torch
                with torch.no_grad():
                    inp = torch.from_numpy(batch_input)
                    out = self._model(inp)
                    if isinstance(out, torch.Tensor):
                        raw_pred = float(torch.sigmoid(out).flatten()[0].item())
                    else:
                        raw_pred = float(out[0])

            tampered = raw_pred >= 0.5
            confidence = raw_pred if tampered else (1.0 - raw_pred)

            res = AIModelForensicResult(
                status=ModelStatus.MODEL_AVAILABLE,
                model_name="Generic_Tampering_Detector",
                version="1.0.0",
                weights_path=self.weights_path,
                confidence=confidence,
                tampering_detected=tampered,
                explanation=(
                    f"AI model predicted manipulation anomaly with confidence {confidence:.2f}."
                    if tampered
                    else f"AI model evaluated document as authentic with confidence {confidence:.2f}."
                ),
            )

            finding = ForensicFinding(
                finding_id="ai_model_01",
                signal_type=SignalType.AI_TAMPERING_MODEL,
                status=SignalStatus.SUSPICIOUS if tampered else SignalStatus.NORMAL,
                severity=SignalSeverity.HIGH if tampered else SignalSeverity.LOW,
                confidence=confidence,
                score=raw_pred,
                source="deep_learning_model",
                model_version="1.0.0",
                explanation=res.explanation,
                metrics={"raw_prediction": raw_pred},
            )
            return res, finding

        except Exception as exc:
            logger.error("DocumentTamperingModel: inference raised exception: %s", exc)
            res = AIModelForensicResult(
                status=ModelStatus.MODEL_INFERENCE_FAILED,
                model_name="Generic_Tampering_Detector",
                version="1.0.0",
                weights_path=self.weights_path,
                confidence=None,
                tampering_detected=None,
                explanation=f"AI model inference failed during execution: {exc}",
            )
            finding = ForensicFinding(
                finding_id="ai_model_01",
                signal_type=SignalType.AI_TAMPERING_MODEL,
                status=SignalStatus.INSUFFICIENT_DATA,
                severity=SignalSeverity.LOW,
                confidence=0.0,
                source="deep_learning_model",
                model_version="1.0.0",
                explanation=res.explanation,
                metrics={"error": str(exc)},
            )
            return res, finding
