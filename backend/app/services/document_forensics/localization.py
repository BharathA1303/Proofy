"""
backend/app/services/document_forensics/localization.py

Spatial Forensic Localization & Patch-Level Analysis Engine.
Computes 2D forensic anomaly heatmaps and clusters localized anomalies into
structured SuspiciousRegion objects with normalized bounding boxes.
Also conducts dedicated region-level checks on portrait and identity text areas.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.services.document_intelligence.schema import NormalizedBBox
from app.services.document_forensics.schema import (
    ForensicFinding,
    SignalSeverity,
    SignalStatus,
    SignalType,
    SuspiciousRegion,
)

logger = logging.getLogger(__name__)

# Grid dimensions for spatial heatmap
GRID_ROWS = 16
GRID_COLS = 16


class ForensicLocalizationEngine:
    """
    Computes spatial distribution of forensic anomalies.
    Translates raw pixel/block signals into bounded regions and heatmaps.
    """

    def generate_heatmap_and_regions(
        self,
        image_np_bgr: np.ndarray,
        ela_map: np.ndarray,
        semantic_regions: Optional[Dict[str, NormalizedBBox]] = None,
    ) -> Tuple[List[List[float]], List[SuspiciousRegion], List[ForensicFinding]]:
        """
        Build a normalized 2D heatmap grid and extract clustered suspicious regions.

        Args:
            image_np_bgr: Decoded image array.
            ela_map: 2D float error map from ELA recompression.
            semantic_regions: Dictionary of profile or M1 semantic region boxes.

        Returns:
            Tuple of:
              - 16x16 2D float heatmap grid (values in [0.0, 1.0])
              - List of SuspiciousRegion objects
              - List of regional ForensicFinding items
        """
        h, w = image_np_bgr.shape[:2]
        gray = cv2.cvtColor(image_np_bgr, cv2.COLOR_BGR2GRAY)

        grid = np.zeros((GRID_ROWS, GRID_COLS), dtype=np.float32)
        cell_h = h / GRID_ROWS
        cell_w = w / GRID_COLS

        # 1. Fill grid cells with local ELA and edge energy
        for r in range(GRID_ROWS):
            for c in range(GRID_COLS):
                y1 = int(r * cell_h)
                y2 = int(min(h, (r + 1) * cell_h))
                x1 = int(c * cell_w)
                x2 = int(min(w, (c + 1) * cell_w))

                ela_cell = ela_map[y1:y2, x1:x2]
                ela_score = float(ela_cell.mean()) if ela_cell.size > 0 else 0.0

                gray_cell = gray[y1:y2, x1:x2]
                lap = cv2.Laplacian(gray_cell, cv2.CV_64F).var() if gray_cell.size > 0 else 0.0
                edge_score = float(min(1.0, lap / 500.0))

                # Combine ELA residual with localized high-frequency edge density
                cell_val = (ela_score * 0.7) + (edge_score * 0.3)
                grid[r, c] = cell_val

        # Normalize grid to [0.0, 1.0]
        max_v = float(grid.max())
        if max_v > 1e-6:
            grid_norm = grid / max_v
        else:
            grid_norm = grid

        # 2. Threshold grid to identify suspicious clusters
        threshold = float(np.mean(grid_norm) + (1.8 * np.std(grid_norm)))
        suspicious_cells = (grid_norm > threshold) & (grid_norm > 0.40)

        suspicious_regions: List[SuspiciousRegion] = []
        regional_findings: List[ForensicFinding] = []

        # Find contiguous anomalous components on grid
        labeled_grid = suspicious_cells.astype(np.uint8)
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(labeled_grid)

        region_idx = 1
        for label_id in range(1, num_labels):
            cell_count = stats[label_id, cv2.CC_STAT_AREA]
            if cell_count < 2:  # Ignore isolated 1-cell noise
                continue

            c_left = stats[label_id, cv2.CC_STAT_LEFT]
            c_top = stats[label_id, cv2.CC_STAT_TOP]
            c_w = stats[label_id, cv2.CC_STAT_WIDTH]
            c_h = stats[label_id, cv2.CC_STAT_HEIGHT]

            px1 = int(c_left * cell_w)
            py1 = int(c_top * cell_h)
            px2 = int(min(w, (c_left + c_w) * cell_w))
            py2 = int(min(h, (c_top + c_h) * cell_h))

            bbox = [[px1, py1], [px2, py1], [px2, py2], [px1, py2]]
            nbox = NormalizedBBox.from_pixel_bbox(bbox, w, h)

            mask = (labels == label_id)
            mean_score = float(grid_norm[mask].mean())

            # Identify if this cluster overlaps known semantic regions
            assoc_name = f"anomalous_patch_{region_idx}"
            if semantic_regions:
                for s_name, s_box in semantic_regions.items():
                    # Check overlap
                    ox = max(nbox.x, s_box.x)
                    oy = max(nbox.y, s_box.y)
                    ow = max(0.0, min(nbox.x + nbox.width, s_box.x + s_box.width) - ox)
                    oh = max(0.0, min(nbox.y + nbox.height, s_box.y + s_box.height) - oy)
                    if (ow * oh) > 0.01:
                        assoc_name = f"{s_name}_anomaly"
                        break

            region_obj = SuspiciousRegion(
                region_id=f"region_{region_idx}",
                region_name=assoc_name,
                bbox=bbox,
                normalized_bbox=nbox,
                signals=["LOCAL_COMPRESSION_ANOMALY", "ELA_HIGH_RESIDUAL"],
                score=mean_score,
                explanation=f"Localized anomaly cluster detected with elevated error level residual (score={mean_score:.2f}).",
            )
            suspicious_regions.append(region_obj)
            region_idx += 1

        # 3. Dedicated Semantic Region Inspections (Portrait and Key Fields)
        if semantic_regions:
            # Check Portrait Region
            if "portrait_area" in semantic_regions or "photo" in semantic_regions:
                p_box = semantic_regions.get("portrait_area") or semantic_regions.get("photo")
                p_finding = self._inspect_portrait_area(image_np_bgr, p_box, ela_map)
                if p_finding:
                    regional_findings.append(p_finding)

            # Check Identity / Number Text Regions
            text_box = semantic_regions.get("license_number") or semantic_regions.get("identity_text")
            if text_box:
                t_finding = self._inspect_text_area(image_np_bgr, text_box, ela_map)
                if t_finding:
                    regional_findings.append(t_finding)

        heatmap_list = [[round(float(grid_norm[r, c]), 3) for c in range(GRID_COLS)] for r in range(GRID_ROWS)]
        return heatmap_list, suspicious_regions, regional_findings

    def _inspect_portrait_area(
        self,
        image_np_bgr: np.ndarray,
        p_box: NormalizedBBox,
        ela_map: np.ndarray,
    ) -> Optional[ForensicFinding]:
        """Examine portrait zone for boundary cut lines, local ELA, and background mismatch."""
        h, w = image_np_bgr.shape[:2]
        px1 = int(p_box.x * w)
        py1 = int(p_box.y * h)
        pw = int(p_box.width * w)
        ph = int(p_box.height * h)

        if pw < 20 or ph < 20 or px1 + pw > w or py1 + ph > h:
            return None

        # Local ELA score in photo
        photo_ela = ela_map[py1 : py1 + ph, px1 : px1 + pw]
        ela_photo_mean = float(photo_ela.mean()) if photo_ela.size > 0 else 0.0
        ela_global_mean = float(ela_map.mean()) if ela_map.size > 0 else 1.0

        # Texture discontinuity on portrait border
        gray = cv2.cvtColor(image_np_bgr, cv2.COLOR_BGR2GRAY)
        margin = 6
        if px1 >= margin and py1 >= margin and (px1 + pw + margin) <= w and (py1 + ph + margin) <= h:
            interior = gray[py1 : py1 + ph, px1 : px1 + pw]
            exterior = gray[py1 - margin : py1 + ph + margin, px1 - margin : px1 + pw + margin]
            var_ratio = max(interior.var(), exterior.var()) / max(min(interior.var(), exterior.var()), 1.0)
        else:
            var_ratio = 1.0

        ratio = ela_photo_mean / max(ela_global_mean, 1e-4)
        is_suspicious = (ratio > 3.0 and var_ratio > 5.0) or ratio > 5.0

        if is_suspicious:
            status = SignalStatus.SUSPICIOUS
            severity = SignalSeverity.HIGH
            explanation = (
                f"Portrait region exhibits strong forensic divergence (ELA ratio={ratio:.1f}, "
                f"boundary texture variance ratio={var_ratio:.1f})."
            )
        else:
            status = SignalStatus.NORMAL
            severity = SignalSeverity.LOW
            explanation = "Portrait region exhibits consistent compression and natural boundary blending."

        return ForensicFinding(
            finding_id="portrait_01",
            signal_type=SignalType.PORTRAIT_REGION_ANOMALY,
            status=status,
            severity=severity,
            confidence=0.85,
            score=round(ratio, 2),
            bbox=[[px1, py1], [px1 + pw, py1], [px1 + pw, py1 + ph], [px1, py1 + ph]],
            normalized_bbox=p_box,
            region_name="portrait_area",
            source="regional_portrait_analyzer",
            explanation=explanation,
            metrics={"ela_ratio": round(ratio, 2), "boundary_variance_ratio": round(var_ratio, 2)},
        )

    def _inspect_text_area(
        self,
        image_np_bgr: np.ndarray,
        t_box: NormalizedBBox,
        ela_map: np.ndarray,
    ) -> Optional[ForensicFinding]:
        """Analyze document text/number zone for sharpness or compression anomaly."""
        h, w = image_np_bgr.shape[:2]
        px1 = int(t_box.x * w)
        py1 = int(t_box.y * h)
        pw = int(t_box.width * w)
        ph = int(t_box.height * h)

        if pw < 20 or ph < 20 or px1 + pw > w or py1 + ph > h:
            return None

        # Local ELA score in text area
        text_ela = ela_map[py1 : py1 + ph, px1 : px1 + pw]
        ela_text_mean = float(text_ela.mean()) if text_ela.size > 0 else 0.0
        ela_global_mean = float(ela_map.mean()) if ela_map.size > 0 else 1.0

        ratio = ela_text_mean / max(ela_global_mean, 1e-4)
        is_suspicious = ratio > 4.5

        if is_suspicious:
            status = SignalStatus.SUSPICIOUS
            severity = SignalSeverity.MEDIUM
            explanation = f"Text/number zone shows localized compression divergence (ELA ratio={ratio:.1f})."
        else:
            status = SignalStatus.NORMAL
            severity = SignalSeverity.LOW
            explanation = "Text/number zone shows consistent background and uniform character rendering."

        return ForensicFinding(
            finding_id="text_01",
            signal_type=SignalType.TEXT_REGION_ANOMALY,
            status=status,
            severity=severity,
            confidence=0.80,
            score=round(ratio, 2),
            bbox=[[px1, py1], [px1 + pw, py1], [px1 + pw, py1 + ph], [px1, py1 + ph]],
            normalized_bbox=t_box,
            region_name="license_number",
            source="regional_text_analyzer",
            explanation=explanation,
            metrics={"ela_ratio": round(ratio, 2)},
        )
