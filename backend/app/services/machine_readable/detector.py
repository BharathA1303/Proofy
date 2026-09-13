"""
backend/app/services/machine_readable/detector.py

OpenCV-based Generic Computer Vision QR and 2D Barcode Detector.
Localizes QR codes on document credentials, extracts polygonal coordinates,
converts to normalized bounding boxes, and detects multiple/corrupted codes.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image

from app.services.document_intelligence.schema import NormalizedBBox
from app.services.machine_readable.schema import QRCandidate, QRDetectionStatus

logger = logging.getLogger(__name__)


def _to_cv2_image(image_input: Union[np.ndarray, Image.Image, bytes, str, Path]) -> Tuple[np.ndarray, int, int]:
    """Convert any supported image format to a BGR numpy array with (width, height)."""
    if isinstance(image_input, np.ndarray):
        img = image_input
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        elif img.ndim == 3 and img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        h, w = img.shape[:2]
        return img, w, h

    if isinstance(image_input, Image.Image):
        rgb = np.array(image_input.convert("RGB"))
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        h, w = bgr.shape[:2]
        return bgr, w, h

    if isinstance(image_input, bytes):
        nparr = np.frombuffer(image_input, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Failed to decode image bytes into valid OpenCV image.")
        h, w = img.shape[:2]
        return img, w, h

    if isinstance(image_input, (str, Path)):
        p = Path(image_input)
        if not p.exists():
            raise FileNotFoundError(f"Image path not found: {image_input}")
        img = cv2.imread(str(p))
        if img is None:
            raise ValueError(f"OpenCV could not read image at path: {image_input}")
        h, w = img.shape[:2]
        return img, w, h

    raise TypeError(f"Unsupported image input type: {type(image_input)}")


def _compute_bbox_overlap(box_a: NormalizedBBox, box_b: NormalizedBBox) -> float:
    """Compute Intersection-over-Union (IoU) of two normalized bounding boxes."""
    x1 = max(box_a.x, box_b.x)
    y1 = max(box_a.y, box_b.y)
    x2 = min(box_a.x + box_a.width, box_b.x + box_b.width)
    y2 = min(box_a.y + box_a.height, box_b.y + box_b.height)

    inter_w = max(0.0, x2 - x1)
    inter_h = max(0.0, y2 - y1)
    inter_area = inter_w * inter_h

    area_a = box_a.width * box_a.height
    area_b = box_b.width * box_b.height
    union_area = area_a + area_b - inter_area
    if union_area <= 0.0:
        return 0.0
    return inter_area / union_area


class QRDetector:
    """
    Robust generic computer vision QR code detector using OpenCV.
    Identifies single or multiple QR codes, records bounding boxes,
    and classifies detection vs decodability status.
    """

    def __init__(self) -> None:
        self._cv2_detector = cv2.QRCodeDetector()

    def _scan_patch(self, patch: np.ndarray, offset_x: int = 0, offset_y: int = 0) -> List[Tuple[np.ndarray, str]]:
        """Run multi and single detection passes on an image patch."""
        if patch is None or patch.size == 0 or patch.shape[0] < 20 or patch.shape[1] < 20:
            return []

        results: List[Tuple[np.ndarray, str]] = []

        # 1. detectAndDecodeMulti
        ret_m, txts, pts_m, _ = self._cv2_detector.detectAndDecodeMulti(patch)
        if ret_m and pts_m is not None and len(pts_m) > 0:
            for i in range(len(pts_m)):
                p = pts_m[i].copy().reshape(-1, 2)
                p[:, 0] += offset_x
                p[:, 1] += offset_y
                results.append((p, txts[i] if i < len(txts) else ""))
            return results

        # 2. detectAndDecode (single)
        txt_s, pts_s, _ = self._cv2_detector.detectAndDecode(patch)
        if pts_s is not None and len(pts_s) > 0:
            p = pts_s.copy().reshape(-1, 2)
            p[:, 0] += offset_x
            p[:, 1] += offset_y
            results.append((p, txt_s or ""))
            return results

        # 3. detect (single without decode)
        ret_d, pts_d = self._cv2_detector.detect(patch)
        if ret_d and pts_d is not None and len(pts_d) > 0:
            p = pts_d.copy().reshape(-1, 2)
            p[:, 0] += offset_x
            p[:, 1] += offset_y
            results.append((p, ""))
            return results

        return results

    def detect_and_decode(
        self,
        image_input: Union[np.ndarray, Image.Image, bytes, str, Path],
        expected_region: Optional[NormalizedBBox] = None,
        side: Optional[str] = None,
        expected_side: Optional[str] = None,
    ) -> Tuple[QRDetectionStatus, List[QRCandidate], Optional[QRCandidate], List[str]]:
        """
        Detect and attempt to decode all QR codes present in the image.

        Args:
            image_input: Image in any supported format.
            expected_region: Expected location bounding box from document profile.
            side: Provided side ('front', 'back', 'unknown').
            expected_side: Expected side from profile ('front', 'back', 'any').

        Returns:
            Tuple of:
              - overall QRDetectionStatus
              - List of all QRCandidate objects
              - primary QRCandidate (or None)
              - List of warning messages
        """
        warnings: List[str] = []

        # Validate side requirement if specified
        if expected_side and side and expected_side not in ("any", "unknown"):
            if side.lower() != expected_side.lower():
                warnings.append(
                    f"QR code side check: document face is '{side}', but expected side is '{expected_side}'"
                )

        try:
            img, img_w, img_h = _to_cv2_image(image_input)
        except Exception as exc:
            warnings.append(f"Image preprocessing failed: {exc}")
            return QRDetectionStatus.NOT_DETECTED, [], None, warnings

        candidates: List[QRCandidate] = []

        # Collect detections across full image and targeted patches
        all_raw_detections: List[Tuple[np.ndarray, str]] = []

        # 1. Full image scan
        all_raw_detections.extend(self._scan_patch(img, 0, 0))

        # 2. Expected region scan (if specified)
        if expected_region:
            rx = int(max(0.0, expected_region.x - 0.05) * img_w)
            ry = int(max(0.0, expected_region.y - 0.05) * img_h)
            rw = int(min(1.0 - (rx / img_w), expected_region.width + 0.10) * img_w)
            rh = int(min(1.0 - (ry / img_h), expected_region.height + 0.10) * img_h)
            if rw > 20 and rh > 20:
                crop = img[ry : ry + rh, rx : rx + rw]
                all_raw_detections.extend(self._scan_patch(crop, rx, ry))

        # 3. Quadrant / halves scan (for multi-QR cards)
        half_patches = [
            (0, 0, img_w // 2, img_h),
            (img_w // 2, 0, img_w, img_h),
            (0, 0, img_w, img_h // 2),
            (0, img_h // 2, img_w, img_h),
        ]
        for px1, py1, px2, py2 in half_patches:
            sub = img[py1:py2, px1:px2]
            all_raw_detections.extend(self._scan_patch(sub, px1, py1))

        # 4. If still nothing detected, try grayscale contrast equalization on full image
        if not all_raw_detections:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            enhanced_bgr = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
            all_raw_detections.extend(self._scan_patch(enhanced_bgr, 0, 0))

        # Deduplicate detections by center-point Euclidean distance
        unique_detections: List[Tuple[np.ndarray, str]] = []
        for pts, txt in all_raw_detections:
            center = np.mean(pts, axis=0)
            matched_idx = None
            for u_idx, (u_pts, u_txt) in enumerate(unique_detections):
                u_center = np.mean(u_pts, axis=0)
                if np.linalg.norm(center - u_center) < (min(img_w, img_h) * 0.08):
                    matched_idx = u_idx
                    break

            if matched_idx is None:
                unique_detections.append((pts, txt))
            elif not unique_detections[matched_idx][1] and txt:
                # Upgrade undecoded candidate with decoded candidate
                unique_detections[matched_idx] = (pts, txt)

        if not unique_detections:
            return QRDetectionStatus.NOT_DETECTED, [], None, warnings

        detected_pts = [d[0] for d in unique_detections]
        decoded_texts = [d[1] for d in unique_detections]

        # Build QRCandidate objects
        for idx, pts in enumerate(detected_pts):
            text = decoded_texts[idx] if idx < len(decoded_texts) else ""

            # Ensure pts shape is (4, 2)
            pts_flat = pts.reshape(-1, 2)
            xs = [int(p[0]) for p in pts_flat]
            ys = [int(p[1]) for p in pts_flat]

            min_x, max_x = max(0, min(xs)), min(img_w, max(xs))
            min_y, max_y = max(0, min(ys)), min(img_h, max(ys))
            pixel_bbox = [[min_x, min_y], [max_x, min_y], [max_x, max_y], [min_x, max_y]]
            norm_bbox = NormalizedBBox.from_pixel_bbox(pixel_bbox, img_w, img_h)

            if text and len(text.strip()) > 0:
                cand_status = QRDetectionStatus.DECODED
                raw_payload: Optional[str] = text
                payload_bytes: Optional[bytes] = text.encode("utf-8")
                err_msg: Optional[str] = None
            else:
                cand_status = QRDetectionStatus.DETECTED_NOT_DECODABLE
                raw_payload = None
                payload_bytes = None
                err_msg = "QR pattern detected but payload decoding failed (damaged, low resolution, or distorted)"

            candidate = QRCandidate(
                candidate_id=f"qr_{idx + 1}",
                status=cand_status,
                bbox=norm_bbox,
                pixel_bbox=pixel_bbox,
                raw_payload=raw_payload,
                payload_bytes=payload_bytes,
                side=side,
                confidence=1.0 if cand_status == QRDetectionStatus.DECODED else 0.5,
                is_primary=False,
                error_message=err_msg,
            )
            candidates.append(candidate)

        if len(candidates) > 1:
            warnings.append(f"Multiple QR codes detected on document (count={len(candidates)})")

        # Select primary candidate
        primary_candidate = self._select_primary_candidate(candidates, expected_region)
        if primary_candidate:
            primary_candidate.is_primary = True

            # Region check for primary candidate
            if expected_region:
                overlap = _compute_bbox_overlap(primary_candidate.bbox, expected_region)
                if overlap < 0.05:
                    warnings.append(
                        f"QR code detected outside expected profile region "
                        f"(overlap={overlap:.2f}, expected={expected_region}, actual={primary_candidate.bbox})"
                    )

        # Determine overall detection status
        has_decoded = any(c.status == QRDetectionStatus.DECODED for c in candidates)
        if has_decoded:
            overall_status = QRDetectionStatus.DECODED
        elif candidates:
            overall_status = QRDetectionStatus.DETECTED_NOT_DECODABLE
        else:
            overall_status = QRDetectionStatus.NOT_DETECTED

        return overall_status, candidates, primary_candidate, warnings

    def _select_primary_candidate(
        self,
        candidates: List[QRCandidate],
        expected_region: Optional[NormalizedBBox] = None,
    ) -> Optional[QRCandidate]:
        """Rank and select the most credible primary QR candidate."""
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        def score_candidate(c: QRCandidate) -> float:
            score = 0.0
            # Strongly prioritize decodable codes
            if c.status == QRDetectionStatus.DECODED:
                score += 100.0
            # Prioritize matching expected region
            if expected_region:
                overlap = _compute_bbox_overlap(c.bbox, expected_region)
                score += overlap * 50.0
            # Prioritize larger area
            area = c.bbox.width * c.bbox.height
            score += area * 10.0
            return score

        candidates_sorted = sorted(candidates, key=score_candidate, reverse=True)
        return candidates_sorted[0]
