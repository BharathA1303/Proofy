"""
backend/app/services/face/minifasnet_pad.py

Presentation Attack Detection (PAD) engine powered by MiniFASNetV2.
Ref: Minivision Silent-Face-Anti-Spoofing.

Complies with ISO/IEC 30107-3 presentation-attack detection concepts.
Distinguishes bona fide human biometric presentation from presentation attacks
(printed paper photos, digital screen replays, cutouts).
"""
from __future__ import annotations

import logging
import math
import os
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.core.config import settings
from app.services.face.minifasnet_model import MiniFASNetV2
from app.services.face.pad_interface import PADAssessment, PresentationAttackDetector

logger = logging.getLogger(__name__)


class MiniFASNetPAD(PresentationAttackDetector):
    """
    MiniFASNet Presentation Attack Detection engine.
    Performs deep convolutional inference on scaled face patches to detect spoofing.
    """

    def __init__(self, model_path: Optional[str] = None, scale: float = 2.7) -> None:
        self._model_path = model_path or settings.MINIFASNET_MODEL_PATH
        self._scale = scale or settings.MINIFASNET_SCALE
        self._model = None
        self._initialized = False
        self._torch = None
        self.initialize()

    def initialize(self) -> None:
        """Load pretrained MiniFASNet PyTorch weights."""
        if not self._model_path or not os.path.exists(self._model_path):
            logger.warning(
                "MiniFASNet model file not found at '%s'. PAD will report MODEL_UNAVAILABLE.",
                self._model_path,
            )
            self._initialized = False
            return

        try:
            import torch
            self._torch = torch

            logger.info("Initializing MiniFASNet PAD model from '%s'...", self._model_path)
            model = MiniFASNetV2(embedding_size=128, conv6_kernel=(5, 5), num_classes=3)
            state_dict = torch.load(self._model_path, map_location="cpu")

            # Strip 'module.' prefix if model was trained with DataParallel
            cleaned_sd = {}
            for k, v in state_dict.items():
                name = k[7:] if k.startswith("module.") else k
                cleaned_sd[name] = v

            model.load_state_dict(cleaned_sd)
            model.eval()
            self._model = model
            self._initialized = True
            logger.info("MiniFASNet PAD model initialized successfully.")
        except Exception as exc:
            logger.error("Failed to load MiniFASNet model: %s", exc, exc_info=True)
            self._model = None
            self._initialized = False

    def is_available(self) -> bool:
        return self._initialized and self._model is not None

    def model_info(self) -> Dict[str, Any]:
        return {
            "model_name": settings.ANTI_SPOOF_MODEL_NAME,
            "architecture": "MiniFASNetV2",
            "input_scale": self._scale,
            "input_size": [80, 80],
            "available": self.is_available(),
            "threshold": settings.ANTI_SPOOF_THRESHOLD,
        }

    @staticmethod
    def _crop_scaled_patch(
        org_img: np.ndarray,
        bbox: Tuple[int, int, int, int],
        scale: float,
        out_w: int = 80,
        out_h: int = 80,
    ) -> np.ndarray:
        """
        Crop context-expanded facial region for MiniFASNet multi-scale classification.
        Matches Silent-Face-Anti-Spoofing patch generator.
        """
        src_h, src_w = org_img.shape[:2]
        x, y, box_w, box_h = bbox

        scale = min((src_h - 1) / max(box_h, 1), min((src_w - 1) / max(box_w, 1), scale))
        new_width = box_w * scale
        new_height = box_h * scale
        center_x = box_w / 2.0 + x
        center_y = box_h / 2.0 + y

        left_top_x = center_x - new_width / 2.0
        left_top_y = center_y - new_height / 2.0
        right_bottom_x = center_x + new_width / 2.0
        right_bottom_y = center_y + new_height / 2.0

        if left_top_x < 0:
            right_bottom_x -= left_top_x
            left_top_x = 0
        if left_top_y < 0:
            right_bottom_y -= left_top_y
            left_top_y = 0
        if right_bottom_x > src_w - 1:
            left_top_x -= right_bottom_x - src_w + 1
            right_bottom_x = src_w - 1
        if right_bottom_y > src_h - 1:
            left_top_y -= right_bottom_y - src_h + 1
            right_bottom_y = src_h - 1

        x1 = max(0, int(left_top_x))
        y1 = max(0, int(left_top_y))
        x2 = min(src_w, int(right_bottom_x) + 1)
        y2 = min(src_h, int(right_bottom_y) + 1)

        patch = org_img[y1:y2, x1:x2]
        if patch.size == 0:
            return cv2.resize(org_img, (out_w, out_h))
        return cv2.resize(patch, (out_w, out_h))

    def _predict_crop(self, patch_80x80: np.ndarray) -> Tuple[float, float, float]:
        """
        Execute MiniFASNet forward pass on a single 80x80 BGR image.
        Returns: (p_spoof, p_real, p_background)
        """
        torch = self._torch
        # MiniFASNet expects (N, 3, H, W) normalized to [0, 1] via ToTensor
        img_rgb = cv2.cvtColor(patch_80x80, cv2.COLOR_BGR2RGB)
        tensor = torch.from_numpy(img_rgb.transpose(2, 0, 1)).float().div(255.0).unsqueeze(0)

        with torch.no_grad():
            logits = self._model(tensor)
            probs = torch.softmax(logits, dim=1).cpu().numpy()[0]

        p_spoof = float(probs[0])
        p_real = float(probs[1])
        p_bg = float(probs[2])
        return p_spoof, p_real, p_bg

    def predict(
        self,
        face_crop: np.ndarray,
        bbox: Optional[Tuple[int, int, int, int]] = None,
        original_img: Optional[np.ndarray] = None,
    ) -> PADAssessment:
        """
        Evaluate presentation attack indicators on a single live face capture.
        """
        if not self.is_available():
            return PADAssessment(
                status="model_unavailable",
                score=None,
                model_name=settings.ANTI_SPOOF_MODEL_NAME,
                explanation="MiniFASNet model weights are not loaded. Biometric PAD model unavailable.",
            )

        if face_crop is None or face_crop.size == 0:
            return PADAssessment(
                status="inconclusive",
                score=None,
                model_name=settings.ANTI_SPOOF_MODEL_NAME,
                explanation="Empty facial image provided for anti-spoof evaluation.",
            )

        try:
            # Prepare scaled patch
            if original_img is not None and bbox is not None and bbox[2] > 0 and bbox[3] > 0:
                patch = self._crop_scaled_patch(original_img, bbox, self._scale, 80, 80)
            else:
                patch = cv2.resize(face_crop, (80, 80))

            p_spoof, p_real, p_bg = self._predict_crop(patch)

            # Calibrated liveness probability (class 1 is bona fide human)
            score = round(float(p_real), 4)

            details = {
                "p_genuine": round(p_real, 4),
                "p_spoof": round(p_spoof, 4),
                "p_background": round(p_bg, 4),
                "threshold": settings.ANTI_SPOOF_THRESHOLD,
            }

            if score >= settings.ANTI_SPOOF_THRESHOLD:
                status = "pass"
                explanation = f"Bona fide human presence verified by MiniFASNet (liveness score: {score:.3f})"
            elif score <= settings.ANTI_SPOOF_SUSPECT_THRESHOLD or p_spoof > 0.50:
                status = "suspected_spoof"
                explanation = f"Presentation attack detected by MiniFASNet (spoof probability: {p_spoof:.3f})"
            else:
                status = "inconclusive"
                explanation = f"Presentation attack assessment inconclusive (liveness score: {score:.3f})"

            return PADAssessment(
                status=status,
                score=score,
                model_name=settings.ANTI_SPOOF_MODEL_NAME,
                explanation=explanation,
                details=details,
            )
        except Exception as exc:
            logger.error("MiniFASNet inference failed: %s", exc, exc_info=True)
            return PADAssessment(
                status="inconclusive",
                score=None,
                model_name=settings.ANTI_SPOOF_MODEL_NAME,
                explanation=f"PAD model inference error: {exc}",
            )

    def predict_sequence(
        self,
        sequence_items: List[Tuple[np.ndarray, Optional[Tuple[int, int, int, int]], Optional[np.ndarray]]],
    ) -> PADAssessment:
        """
        Aggregate PAD assessments across multiple consecutive burst frames.
        """
        if not self.is_available():
            return self.predict(None)

        if not sequence_items:
            return PADAssessment(
                status="inconclusive",
                score=None,
                model_name=settings.ANTI_SPOOF_MODEL_NAME,
                explanation="No sequence frames provided for temporal PAD evaluation.",
            )

        scores = []
        spoof_probs = []
        for crop, bbox, orig in sequence_items:
            res = self.predict(crop, bbox, orig)
            if res.score is not None:
                scores.append(res.score)
            if "p_spoof" in res.details:
                spoof_probs.append(res.details["p_spoof"])

        if not scores:
            return PADAssessment(
                status="inconclusive",
                score=None,
                model_name=settings.ANTI_SPOOF_MODEL_NAME,
                explanation="Temporal PAD evaluation yielded no valid frame scores.",
            )

        # Robust aggregation: median score across burst
        med_score = round(float(np.median(scores)), 4)
        max_spoof = round(float(np.max(spoof_probs)), 4) if spoof_probs else 0.0

        details = {
            "burst_frame_count": len(scores),
            "median_liveness_score": med_score,
            "max_spoof_prob": max_spoof,
            "individual_scores": scores,
            "threshold": settings.ANTI_SPOOF_THRESHOLD,
        }

        if med_score >= settings.ANTI_SPOOF_THRESHOLD and max_spoof < 0.50:
            status = "pass"
            explanation = f"Bona fide human presence verified across {len(scores)} burst frames (median liveness: {med_score:.3f})"
        elif med_score <= settings.ANTI_SPOOF_SUSPECT_THRESHOLD or max_spoof >= 0.60:
            status = "suspected_spoof"
            explanation = f"Presentation attack detected across temporal burst sequence (peak spoof prob: {max_spoof:.3f})"
        else:
            status = "inconclusive"
            explanation = f"Multi-frame PAD evaluation inconclusive (median score: {med_score:.3f})"

        return PADAssessment(
            status=status,
            score=med_score,
            model_name=settings.ANTI_SPOOF_MODEL_NAME,
            explanation=explanation,
            details=details,
        )
