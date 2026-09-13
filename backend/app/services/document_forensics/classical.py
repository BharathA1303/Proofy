"""
backend/app/services/document_forensics/classical.py

Deterministic Classical Forensic Analysis Engines.
Implements:
  1. Error Level Analysis (ELA) with per-block outlier localization
  2. JPEG Compression Blockiness Consistency Analysis
  3. Spatial Copy-Move / Duplication Detection via Keypoint Offset Clustering
  4. Boundary and Splicing Edge Discontinuity Analysis
  5. Document Card Boundary Geometric Localization
  6. EXIF and File Metadata Forensic Verification
"""
from __future__ import annotations

import io
import logging
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image
from PIL.ExifTags import TAGS

from app.services.document_intelligence.schema import NormalizedBBox
from app.services.document_forensics.schema import (
    DocumentBoundaryResult,
    ForensicFinding,
    SignalSeverity,
    SignalStatus,
    SignalType,
)

logger = logging.getLogger(__name__)

# Configurable constants
DEFAULT_ELA_JPEG_QUALITY = 90
DEFAULT_ELA_BLOCK_SIZE = 32
DEFAULT_ELA_OUTLIER_K = 2.5
DEFAULT_ELA_SUSPICIOUS_RATIO = 0.02

# Compression blockiness
JPEG_BLOCK = 8
DEFAULT_COMPRESSION_RATIO_SUSPICIOUS = 5.0
DEFAULT_COMPRESSION_RATIO_HIGH = 10.0

# Copy-move
DEFAULT_COPY_MOVE_MIN_MATCHES = 8
DEFAULT_COPY_MOVE_MIN_DIST = 40.0

# Software editor signatures in EXIF
KNOWN_IMAGE_EDITORS = [
    "photoshop", "gimp", "paint.net", "canva", "picsart",
    "snapseed", "pixlr", "affinity", "lightroom", "coreldraw",
]


class ClassicalForensicEngine:
    """
    Executes independent classical image forensic detectors.
    Outputs structured findings preserving spatial geometry and telemetry.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}

    # ==========================================================================
    # 1. Error Level Analysis (ELA)
    # ==========================================================================
    def run_ela(self, image_np_bgr: np.ndarray) -> Tuple[ForensicFinding, List[Dict[str, Any]], np.ndarray]:
        """
        Execute Error Level Analysis at fixed JPEG recompression quality.

        Returns:
            Tuple of:
              - ForensicFinding
              - List of anomalous block dictionaries with pixel coordinates
              - 2D float error map (normalized [0.0, 1.0])
        """
        h, w = image_np_bgr.shape[:2]
        quality = self.config.get("ela_quality", DEFAULT_ELA_JPEG_QUALITY)
        block_size = self.config.get("ela_block_size", DEFAULT_ELA_BLOCK_SIZE)
        k_thresh = self.config.get("ela_k", DEFAULT_ELA_OUTLIER_K)
        suspicious_ratio = self.config.get("ela_suspicious_ratio", DEFAULT_ELA_SUSPICIOUS_RATIO)

        # JPEG recompression
        success, encoded = cv2.imencode(".jpg", image_np_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not success:
            return (
                ForensicFinding(
                    finding_id="ela_01",
                    signal_type=SignalType.ELA_RESIDUAL,
                    status=SignalStatus.UNAVAILABLE,
                    severity=SignalSeverity.LOW,
                    confidence=0.5,
                    explanation="JPEG recompression failed during ELA.",
                ),
                [],
                np.zeros((h, w), dtype=np.float32),
            )

        recompressed = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        diff = cv2.absdiff(image_np_bgr, recompressed)
        gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY).astype(np.float32)

        mean_err = float(gray_diff.mean())
        std_err = float(gray_diff.std())
        max_err = float(gray_diff.max())
        threshold = mean_err + (k_thresh * std_err)

        anomalous_blocks: List[Dict[str, Any]] = []
        flagged_area = 0

        # Tile grid analysis
        for y in range(0, h, block_size):
            for x in range(0, w, block_size):
                bw = min(block_size, w - x)
                bh = min(block_size, h - y)
                block = gray_diff[y : y + bh, x : x + bw]
                block_mean = float(block.mean())

                if block_mean > threshold:
                    flagged_area += bw * bh
                    anomalous_blocks.append({
                        "x": x,
                        "y": y,
                        "width": bw,
                        "height": bh,
                        "mean_error": round(block_mean, 2),
                    })

        total_area = h * w
        flagged_ratio = float(flagged_area / max(1, total_area))

        is_suspicious = flagged_ratio >= suspicious_ratio
        severity = SignalSeverity.HIGH if flagged_ratio >= (suspicious_ratio * 3) else (
            SignalSeverity.MEDIUM if is_suspicious else SignalSeverity.LOW
        )
        status = SignalStatus.SUSPICIOUS if is_suspicious else SignalStatus.NORMAL

        explanation = (
            f"ELA flagged {len(anomalous_blocks)} blocks ({flagged_ratio * 100:.2f}% of area) "
            f"exceeding recompression variance baseline (mean={mean_err:.2f}, max={max_err:.2f})."
            if is_suspicious
            else "ELA recompression residual is uniform across the document."
        )

        norm_diff = gray_diff / (max_err + 1e-6)

        finding = ForensicFinding(
            finding_id="ela_01",
            signal_type=SignalType.ELA_RESIDUAL,
            status=status,
            severity=severity,
            confidence=0.90,
            score=round(flagged_ratio, 4),
            source="ela_detector",
            explanation=explanation,
            metrics={
                "mean_error": round(mean_err, 2),
                "std_error": round(std_err, 2),
                "max_error": round(max_err, 2),
                "flagged_ratio": round(flagged_ratio, 4),
                "flagged_blocks": len(anomalous_blocks),
            },
        )
        return finding, anomalous_blocks, norm_diff

    # ==========================================================================
    # 2. JPEG Compression Blockiness Analysis
    # ==========================================================================
    def analyze_compression(
        self,
        image_np_bgr: np.ndarray,
        regions: Optional[Dict[str, NormalizedBBox]] = None,
    ) -> ForensicFinding:
        """
        Evaluate JPEG 8x8 blockiness energy ratio consistency across regions.
        """
        h, w = image_np_bgr.shape[:2]
        gray = cv2.cvtColor(image_np_bgr, cv2.COLOR_BGR2GRAY)

        # Region boxes in pixels
        target_regions: Dict[str, Tuple[int, int, int, int]] = {}
        if regions:
            for name, nbox in regions.items():
                px1 = int(nbox.x * w)
                py1 = int(nbox.y * h)
                pw = int(nbox.width * w)
                ph = int(nbox.height * h)
                if pw >= JPEG_BLOCK * 2 and ph >= JPEG_BLOCK * 2:
                    target_regions[name] = (px1, py1, pw, ph)

        # Default regions if none provided
        if len(target_regions) < 2:
            # Region 1: Upper-left (typical photo zone)
            target_regions["zone_left"] = (int(w * 0.05), int(h * 0.20), int(w * 0.30), int(h * 0.45))
            # Region 2: Upper-right (typical text/details zone)
            target_regions["zone_center"] = (int(w * 0.40), int(h * 0.20), int(w * 0.50), int(h * 0.45))
            # Region 3: Background margin
            target_regions["zone_bg"] = (int(w * 0.05), int(h * 0.05), int(w * 0.90), int(h * 0.10))

        scores: Dict[str, float] = {}
        for r_name, (rx, ry, rw, rh) in target_regions.items():
            crop = gray[ry : ry + rh, rx : rx + rw]
            score = self._compute_blockiness(crop)
            if score is not None:
                scores[r_name] = score

        if len(scores) < 2:
            return ForensicFinding(
                finding_id="comp_01",
                signal_type=SignalType.JPEG_COMPRESSION,
                status=SignalStatus.INSUFFICIENT_DATA,
                severity=SignalSeverity.LOW,
                confidence=0.5,
                explanation="Insufficient distinct regions with valid 8x8 blocks for compression analysis.",
            )

        valid_vals = list(scores.values())
        min_score = min(valid_vals)
        max_score = max(valid_vals)
        ratio = max_score / max(min_score, 1e-4)

        suspicious_ratio = self.config.get("compression_ratio_suspicious", DEFAULT_COMPRESSION_RATIO_SUSPICIOUS)
        high_ratio = self.config.get("compression_ratio_high", DEFAULT_COMPRESSION_RATIO_HIGH)

        if ratio >= high_ratio:
            status = SignalStatus.SUSPICIOUS
            severity = SignalSeverity.HIGH
            explanation = (
                f"Severe local compression inconsistency across regions (ratio={ratio:.1f} >= {high_ratio}). "
                "Different areas show divergent JPEG blocking artifacts."
            )
        elif ratio >= suspicious_ratio:
            status = SignalStatus.SUSPICIOUS
            severity = SignalSeverity.MEDIUM
            explanation = (
                f"Moderate local compression inconsistency detected (ratio={ratio:.1f} >= {suspicious_ratio})."
            )
        else:
            status = SignalStatus.NORMAL
            severity = SignalSeverity.LOW
            explanation = f"Compression blockiness is consistent across regions (ratio={ratio:.1f})."

        return ForensicFinding(
            finding_id="comp_01",
            signal_type=SignalType.JPEG_COMPRESSION,
            status=status,
            severity=severity,
            confidence=0.85,
            score=round(ratio, 2),
            source="compression_engine",
            explanation=explanation,
            metrics={"ratio": round(ratio, 2), "scores": {k: round(v, 3) for k, v in scores.items()}},
        )

    def _compute_blockiness(self, gray_crop: np.ndarray) -> Optional[float]:
        """Compute JPEG 8x8 boundary gradient vs interior gradient ratio."""
        h, w = gray_crop.shape[:2]
        if h < JPEG_BLOCK * 2 or w < JPEG_BLOCK * 2:
            return None

        arr = gray_crop.astype(np.float64)
        grad_x = np.abs(np.diff(arr, axis=1))

        boundary_cols = np.arange(JPEG_BLOCK - 1, w - 1, JPEG_BLOCK)
        if boundary_cols.size == 0:
            return None

        mask = np.zeros(grad_x.shape[1], dtype=bool)
        mask[boundary_cols] = True

        b_energy = grad_x[:, mask].mean() if mask.any() else 0.0
        w_energy = grad_x[:, ~mask].mean() if (~mask).any() else 0.0
        if w_energy < 0.2:
            # Low interior texture/gradient; skip flat regions to prevent division by near-zero
            return None
        return float(b_energy / w_energy)

    # ==========================================================================
    # 3. Copy-Move / Duplication Detection
    # ==========================================================================
    def detect_copy_move(self, image_np_bgr: np.ndarray) -> ForensicFinding:
        """
        Detect duplicated / cloned regions using ORB spatial keypoint clustering.
        """
        h, w = image_np_bgr.shape[:2]
        gray = cv2.cvtColor(image_np_bgr, cv2.COLOR_BGR2GRAY)

        orb = cv2.ORB_create(nfeatures=1200)
        keypoints, descriptors = orb.detectAndCompute(gray, None)

        min_matches = self.config.get("copy_move_min_matches", DEFAULT_COPY_MOVE_MIN_MATCHES)
        min_dist = self.config.get("copy_move_min_dist", DEFAULT_COPY_MOVE_MIN_DIST)

        if descriptors is None or len(descriptors) < 20:
            return ForensicFinding(
                finding_id="copymove_01",
                signal_type=SignalType.COPY_MOVE_DUPLICATION,
                status=SignalStatus.NORMAL,
                severity=SignalSeverity.LOW,
                confidence=0.7,
                explanation="Insufficient distinct texture keypoints for copy-move analysis.",
            )

        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        matches = bf.match(descriptors, descriptors)

        # Filter self-matches and nearby matches
        valid_clone_pairs: List[Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]]] = []
        for m in matches:
            if m.queryIdx != m.trainIdx and m.distance < 25:
                pt1 = keypoints[m.queryIdx].pt
                pt2 = keypoints[m.trainIdx].pt
                dist = float(np.hypot(pt2[0] - pt1[0], pt2[1] - pt1[1]))
                if dist >= min_dist:
                    offset = (round(pt2[0] - pt1[0], 1), round(pt2[1] - pt1[1], 1))
                    valid_clone_pairs.append((pt1, pt2, offset))

        # Cluster by offset vector
        offset_clusters: Dict[Tuple[int, int], List[Any]] = {}
        for p1, p2, off in valid_clone_pairs:
            # Quantize offset into 20px bins
            bin_key = (int(off[0] // 20), int(off[1] // 20))
            offset_clusters.setdefault(bin_key, []).append((p1, p2))

        # Find largest cluster
        largest_cluster = max(offset_clusters.values(), key=len) if offset_clusters else []
        cluster_count = len(largest_cluster)

        if cluster_count >= min_matches:
            # Suspicious cloned area identified!
            pts = [p[0] for p in largest_cluster] + [p[1] for p in largest_cluster]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            bbox = [[int(min(xs)), int(min(ys))], [int(max(xs)), int(min(ys))],
                    [int(max(xs)), int(max(ys))], [int(min(xs)), int(max(ys))]]
            nbox = NormalizedBBox.from_pixel_bbox(bbox, w, h)

            return ForensicFinding(
                finding_id="copymove_01",
                signal_type=SignalType.COPY_MOVE_DUPLICATION,
                status=SignalStatus.SUSPICIOUS,
                severity=SignalSeverity.HIGH,
                confidence=0.88,
                score=float(cluster_count),
                bbox=bbox,
                normalized_bbox=nbox,
                source="copy_move_detector",
                explanation=f"Detected {cluster_count} coherent duplicate keypoints indicating potential cloned/copy-moved region.",
                metrics={"matching_pairs": cluster_count},
            )

        return ForensicFinding(
            finding_id="copymove_01",
            signal_type=SignalType.COPY_MOVE_DUPLICATION,
            status=SignalStatus.NORMAL,
            severity=SignalSeverity.LOW,
            confidence=0.85,
            score=float(cluster_count),
            source="copy_move_detector",
            explanation="No suspicious duplicated or cloned texture patterns detected.",
            metrics={"max_cluster": cluster_count},
        )

    # ==========================================================================
    # 4. Splicing / Edge Discontinuity Analysis
    # ==========================================================================
    def analyze_splicing_edges(
        self,
        image_np_bgr: np.ndarray,
        target_box: Optional[NormalizedBBox] = None,
    ) -> ForensicFinding:
        """
        Evaluate edge gradient sharpness and noise variance mismatch across a regional boundary.
        """
        h, w = image_np_bgr.shape[:2]
        gray = cv2.cvtColor(image_np_bgr, cv2.COLOR_BGR2GRAY)

        if target_box is None:
            # Test default portrait / center zone
            target_box = NormalizedBBox(0.05, 0.20, 0.30, 0.50)

        px1 = int(target_box.x * w)
        py1 = int(target_box.y * h)
        pw = int(target_box.width * w)
        ph = int(target_box.height * h)

        margin = 8
        if px1 < margin or py1 < margin or (px1 + pw + margin) > w or (py1 + ph + margin) > h:
            return ForensicFinding(
                finding_id="splicing_01",
                signal_type=SignalType.SPLICING_EDGE,
                status=SignalStatus.NORMAL,
                severity=SignalSeverity.LOW,
                confidence=0.7,
                explanation="Boundary is at image edge; boundary discontinuity analysis skipped.",
            )

        # Interior margin strip vs exterior margin strip
        interior = gray[py1 : py1 + ph, px1 : px1 + pw]
        exterior = gray[py1 - margin : py1 + ph + margin, px1 - margin : px1 + pw + margin]

        int_var = float(interior.var())
        ext_var = float(exterior.var())

        # Sobel gradient on border
        sobel_x = cv2.Sobel(exterior, cv2.CV_64F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(exterior, cv2.CV_64F, 0, 1, ksize=3)
        grad_mag = np.sqrt(sobel_x**2 + sobel_y**2)
        border_grad_mean = float(grad_mag.mean())

        var_ratio = max(int_var, ext_var) / max(min(int_var, ext_var), 1.0)
        is_suspicious = border_grad_mean > 80.0 or var_ratio > 6.0

        if is_suspicious:
            status = SignalStatus.SUSPICIOUS
            severity = SignalSeverity.MEDIUM
            explanation = f"Sharp edge discontinuity and texture mismatch detected along region boundary (gradient={border_grad_mean:.1f}, ratio={var_ratio:.1f})."
        else:
            status = SignalStatus.NORMAL
            severity = SignalSeverity.LOW
            explanation = "Boundary edge transitions and local noise are consistent with surrounding background."

        return ForensicFinding(
            finding_id="splicing_01",
            signal_type=SignalType.SPLICING_EDGE,
            status=status,
            severity=severity,
            confidence=0.80,
            score=round(var_ratio, 2),
            bbox=[[px1, py1], [px1 + pw, py1], [px1 + pw, py1 + ph], [px1, py1 + ph]],
            normalized_bbox=target_box,
            source="splicing_detector",
            explanation=explanation,
            metrics={"variance_ratio": round(var_ratio, 2), "border_gradient": round(border_grad_mean, 2)},
        )

    # ==========================================================================
    # 5. Document Card Boundary Geometric Localization
    # ==========================================================================
    def detect_document_boundary(self, image_np_bgr: np.ndarray) -> DocumentBoundaryResult:
        """
        Locate document perimeter contour, evaluate rectangularity and card aspect ratio.
        """
        h, w = image_np_bgr.shape[:2]
        image_aspect = float(w / max(1, h))

        gray = cv2.cvtColor(image_np_bgr, cv2.COLOR_BGR2GRAY)
        if float(gray.std()) < 5.0:
            return DocumentBoundaryResult(
                status=SignalStatus.BOUNDARY_UNAVAILABLE,
                details="Image is uniform solid color; no document boundary present.",
            )

        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 40, 140)

        # Morphological closing to seal boundary gaps
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        is_full_frame_card = abs(image_aspect - 1.58) <= 0.25

        if not contours:
            if is_full_frame_card:
                return DocumentBoundaryResult(
                    status=SignalStatus.BOUNDARY_DETECTED,
                    contour_points=[[0, 0], [w, 0], [w, h], [0, h]],
                    normalized_bbox=NormalizedBBox(0.0, 0.0, 1.0, 1.0),
                    is_rectangular=True,
                    rectangularity_score=1.0,
                    aspect_ratio=image_aspect,
                    details=f"Document card boundary fills frame (aspect ratio {image_aspect:.2f} matches standard ID-1).",
                )
            return DocumentBoundaryResult(
                status=SignalStatus.BOUNDARY_UNAVAILABLE,
                details="No distinct card boundary detected in image.",
            )

        # Find largest contour with area >= 15% of image
        min_area = (h * w) * 0.15
        valid_contours = [c for c in contours if cv2.contourArea(c) >= min_area]
        if not valid_contours:
            if is_full_frame_card:
                return DocumentBoundaryResult(
                    status=SignalStatus.BOUNDARY_DETECTED,
                    contour_points=[[0, 0], [w, 0], [w, h], [0, h]],
                    normalized_bbox=NormalizedBBox(0.0, 0.0, 1.0, 1.0),
                    is_rectangular=True,
                    rectangularity_score=1.0,
                    aspect_ratio=image_aspect,
                    details=f"Document card boundary fills frame (aspect ratio {image_aspect:.2f} matches standard ID-1).",
                )
            return DocumentBoundaryResult(
                status=SignalStatus.BOUNDARY_UNAVAILABLE,
                details="No candidate contour meets minimum card area threshold (15% of canvas).",
            )

        c = max(valid_contours, key=cv2.contourArea)
        area = cv2.contourArea(c)
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)

        bx, by, bw, bh = cv2.boundingRect(c)
        bbox = [[bx, by], [bx + bw, by], [bx + bw, by + bh], [bx, by + bh]]
        nbox = NormalizedBBox.from_pixel_bbox(bbox, w, h)

        rect_area = bw * bh
        rectangularity = float(area / max(1, rect_area))
        aspect = float(bw / max(1, bh))

        # If the largest contour is an internal element (e.g. photo patch < 40% area) but image is card-shaped
        if (area / (h * w)) < 0.40 and aspect < 1.1 and is_full_frame_card:
            return DocumentBoundaryResult(
                status=SignalStatus.BOUNDARY_DETECTED,
                contour_points=[[0, 0], [w, 0], [w, h], [0, h]],
                normalized_bbox=NormalizedBBox(0.0, 0.0, 1.0, 1.0),
                is_rectangular=True,
                rectangularity_score=1.0,
                aspect_ratio=image_aspect,
                details=f"Document card boundary fills frame (aspect ratio {image_aspect:.2f} matches standard ID-1).",
            )

        is_rect = len(approx) == 4 and rectangularity >= 0.75

        # Check standard card aspect ratio (~1.58 for ID-1)
        aspect_deviation = abs(aspect - 1.58)
        if aspect_deviation > 0.50:
            status = SignalStatus.BOUNDARY_SUSPICIOUS
            details = f"Card boundary localized but exhibits anomalous aspect ratio ({aspect:.2f} vs expected ~1.58)."
        else:
            status = SignalStatus.BOUNDARY_DETECTED
            details = f"Card boundary cleanly localized (rectangularity={rectangularity:.2f}, aspect={aspect:.2f})."

        return DocumentBoundaryResult(
            status=status,
            contour_points=[[int(pt[0][0]), int(pt[0][1])] for pt in approx],
            normalized_bbox=nbox,
            is_rectangular=is_rect,
            rectangularity_score=rectangularity,
            aspect_ratio=aspect,
            details=details,
        )

    # ==========================================================================
    # 6. EXIF and Metadata Analysis
    # ==========================================================================
    def analyze_metadata(self, raw_bytes: bytes) -> ForensicFinding:
        """
        Safely analyze image EXIF metadata for editing software traces.
        Enforces: EXIF_ABSENT is normal, NOT a forgery indicator.
        """
        if not raw_bytes:
            return ForensicFinding(
                finding_id="meta_01",
                signal_type=SignalType.METADATA_EXIF,
                status=SignalStatus.EXIF_UNAVAILABLE,
                severity=SignalSeverity.LOW,
                confidence=0.5,
                explanation="No raw image bytes provided for metadata analysis.",
            )

        try:
            with Image.open(io.BytesIO(raw_bytes)) as pil_img:
                exif_data = pil_img.getexif()
                if not exif_data:
                    return ForensicFinding(
                        finding_id="meta_01",
                        signal_type=SignalType.METADATA_EXIF,
                        status=SignalStatus.EXIF_ABSENT,
                        severity=SignalSeverity.LOW,
                        confidence=0.8,
                        explanation="No EXIF metadata present (standard for mobile uploads, web exports, or scans).",
                    )

                # Parse tags
                meta_dict: Dict[str, Any] = {}
                for tag_id, value in exif_data.items():
                    tag_name = TAGS.get(tag_id, str(tag_id))
                    meta_dict[tag_name] = str(value)

                software_tag = str(meta_dict.get("Software", "")).lower()
                suspicious_editor = None
                for editor in KNOWN_IMAGE_EDITORS:
                    if editor in software_tag:
                        suspicious_editor = editor
                        break

                if suspicious_editor:
                    return ForensicFinding(
                        finding_id="meta_01",
                        signal_type=SignalType.METADATA_EXIF,
                        status=SignalStatus.EXIF_SUSPICIOUS,
                        severity=SignalSeverity.MEDIUM,
                        confidence=0.85,
                        source="exif_analyzer",
                        explanation=f"EXIF Software tag records image manipulation software ('{meta_dict.get('Software')}').",
                        metrics={"software": meta_dict.get("Software")},
                    )

                return ForensicFinding(
                    finding_id="meta_01",
                    signal_type=SignalType.METADATA_EXIF,
                    status=SignalStatus.EXIF_PRESENT,
                    severity=SignalSeverity.LOW,
                    confidence=0.85,
                    source="exif_analyzer",
                    explanation=f"EXIF metadata present ({len(meta_dict)} tags) with no suspicious editing software tags.",
                    metrics={"tag_count": len(meta_dict)},
                )

        except Exception as exc:
            logger.debug("EXIF parsing raised: %s", exc)
            return ForensicFinding(
                finding_id="meta_01",
                signal_type=SignalType.METADATA_EXIF,
                status=SignalStatus.EXIF_UNAVAILABLE,
                severity=SignalSeverity.LOW,
                confidence=0.5,
                explanation=f"Could not read metadata: {exc}",
            )
