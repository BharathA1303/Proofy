"""
backend/app/services/face/scrfd_detector.py

SCRFD deep face detector powered by ONNX Runtime.
Model: InsightFace Buffalo_L det_10g.onnx.
Locates face bounding boxes and predicts 5 facial landmarks for alignment:
  [left_eye, right_eye, nose, left_mouth_corner, right_mouth_corner].
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional, Tuple

import cv2
import numpy as np

from app.services.face.detector_interface import FaceDetectionResult, FaceDetector

logger = logging.getLogger(__name__)


class SCRFDDetector(FaceDetector):
    """
    Sample and Computation Redistribution Face Detector (SCRFD).
    High-accuracy, multi-scale deep convolutional face detector.
    """

    def __init__(self, model_path: str, score_thresh: float = 0.50, nms_thresh: float = 0.40) -> None:
        self._model_path = model_path
        self._score_thresh = score_thresh
        self._nms_thresh = nms_thresh
        self._session = None
        self._strides = [8, 16, 32]
        self._initialized = False
        self.initialize()

    def initialize(self) -> None:
        """Load SCRFD ONNX model into ONNX Runtime CPU session."""
        if not self._model_path or not os.path.exists(self._model_path):
            logger.warning("SCRFD model file not found at '%s'. Detector unavailable.", self._model_path)
            self._initialized = False
            return

        try:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 2
            opts.intra_op_num_threads = 2
            self._session = ort.InferenceSession(
                self._model_path,
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
            self._initialized = True
            logger.info("SCRFDDetector initialized successfully from '%s'.", self._model_path)
        except Exception as exc:
            logger.error("Failed to initialize SCRFD detector: %s", exc, exc_info=True)
            self._session = None
            self._initialized = False

    def is_available(self) -> bool:
        return self._initialized and self._session is not None

    @property
    def model_name(self) -> str:
        return "InsightFace-SCRFD-10G"

    def detect_faces(self, image_bgr: np.ndarray) -> List[FaceDetectionResult]:
        """
        Detect faces and 5 facial landmarks in a BGR image.
        """
        if not self.is_available():
            return []

        if image_bgr is None or image_bgr.size == 0:
            return []

        h_orig, w_orig = image_bgr.shape[:2]
        # Multi-scale letterbox padding to 640x640
        scale = min(640.0 / w_orig, 640.0 / h_orig)
        nw, nh = int(w_orig * scale), int(h_orig * scale)
        resized = cv2.resize(image_bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
        det_img = np.zeros((640, 640, 3), dtype=np.uint8)
        det_img[:nh, :nw] = resized

        blob = (det_img.astype(np.float32) - 127.5) / 128.0
        blob = blob.transpose(2, 0, 1)[np.newaxis, ...]

        try:
            outs = self._session.run(None, {"input.1": blob})
        except Exception as exc:
            logger.error("SCRFD detection inference failed: %s", exc)
            return []

        boxes: List[List[int]] = []
        scores: List[float] = []
        kps_list: List[List[Tuple[float, float]]] = []

        # outs layout: [score_8, score_16, score_32, bbox_8, bbox_16, bbox_32, kps_8, kps_16, kps_32]
        for idx, stride in enumerate(self._strides):
            score_out = outs[idx]      # (N, 1)
            bbox_out = outs[idx + 3]   # (N, 4)
            kps_out = outs[idx + 6]    # (N, 10)

            feat_h = 640 // stride
            feat_w = 640 // stride
            gx, gy = np.meshgrid(np.arange(feat_w), np.arange(feat_h))
            anchor_centers = np.stack([gx, gy], axis=-1).reshape(-1, 2) * stride
            anchor_centers = np.repeat(anchor_centers, 2, axis=0)  # 2 anchors per spatial location

            flat_scores = score_out.flatten()
            pos_inds = np.where(flat_scores >= self._score_thresh)[0]
            if len(pos_inds) == 0:
                continue

            pos_scores = flat_scores[pos_inds]
            pos_bboxes = bbox_out[pos_inds] * stride
            pos_kps = kps_out[pos_inds] * stride
            pos_anchors = anchor_centers[pos_inds]

            x1 = (pos_anchors[:, 0] - pos_bboxes[:, 0]) / scale
            y1 = (pos_anchors[:, 1] - pos_bboxes[:, 1]) / scale
            x2 = (pos_anchors[:, 0] + pos_bboxes[:, 2]) / scale
            y2 = (pos_anchors[:, 1] + pos_bboxes[:, 3]) / scale
            w = x2 - x1
            h = y2 - y1

            for i in range(len(pos_scores)):
                boxes.append([int(x1[i]), int(y1[i]), int(w[i]), int(h[i])])
                scores.append(float(pos_scores[i]))
                kps = []
                for p in range(5):
                    px = (pos_anchors[i, 0] + pos_kps[i, 2 * p]) / scale
                    py = (pos_anchors[i, 1] + pos_kps[i, 2 * p + 1]) / scale
                    kps.append((float(px), float(py)))
                kps_list.append(kps)

        if not boxes:
            return []

        indices = cv2.dnn.NMSBoxes(boxes, scores, self._score_thresh, self._nms_thresh)
        results: List[FaceDetectionResult] = []
        for i in indices:
            idx_int = int(i) if isinstance(i, (int, np.integer)) else int(i[0])
            bx, by, bw, bh = boxes[idx_int]
            # Clamp to original image bounds
            bx = max(0, min(bx, w_orig - 1))
            by = max(0, min(by, h_orig - 1))
            bw = max(1, min(bw, w_orig - bx))
            bh = max(1, min(bh, h_orig - by))
            results.append(
                FaceDetectionResult(
                    bbox=(bx, by, bw, bh),
                    confidence=scores[idx_int],
                    landmarks=kps_list[idx_int],
                )
            )

        return results
