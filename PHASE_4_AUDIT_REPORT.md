# Phase 4 Biometric System Audit & Redesign Strategy

**Date:** September 2026  
**Status:** Audit Complete — Approved for Modular Redesign  

---

## 1. System & Environment Audit Findings

| Component | Current State | Compatibility & Impact on Phase 4 |
|---|---|---|
| **Python** | 3.11.0 (64-bit, Windows AMD64) | Fully compatible with PyTorch CPU and ONNX Runtime. |
| **PyTorch / TorchVision** | `torch==2.12.1+cpu`, `torchvision==0.27.1+cpu` | Operational on local CPU without discrete GPU dependencies. Runs MiniFASNet forward pass in ~35ms. |
| **ONNX Runtime** | `onnxruntime==1.29.0` (CPUExecutionProvider) | Pre-installed and verified. Capable of loading InsightFace ArcFace (`w600k_r50.onnx`) and YuNet in ~150ms on CPU. |
| **OpenCV** | `opencv-python==4.6.0.66` | Contains built-in `cv2.FaceDetectorYN` for YuNet detection + 5 facial landmarks. |
| **PaddleOCR / Protobuf** | `paddleocr==2.7.3`, `protobuf==6.33.6` | Setting `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python` avoids Protobuf descriptor collisions and preserves 100% functionality for Modules 1–3. |
| **Model Assets** | Verified in `backend/app/models_weights/` | 1. `face_detection_yunet_2023mar.onnx` (YuNet 5-landmark face detector)<br>2. `w600k_r50.onnx` (InsightFace ArcFace ResNet-50, 512-D)<br>3. `2.7_80x80_MiniFASNetV2.pth` (Silent-Face-Anti-Spoofing MiniFASNetV2)<br>4. `4_0_0_80x80_MiniFASNetV1SE.pth` (Silent-Face-Anti-Spoofing MiniFASNetV1SE) |

---

## 2. Audit Determinations (Step 0 Requirements)

1. **What currently works:**
   - Modules 1–3 (PaddleOCR ingestion, TD3 MRZ parser, validation check digits, forensic tampering analysis).
   - Module 4 frontend camera lifecycle (`navigator.mediaDevices.getUserMedia()`, manual start, oval guide, burst capture, `track.stop()`).
   - In-memory `SessionDocumentStore` with 15-minute sliding TTL.
   - Deterministic face quality gate (`face_quality.py`).
   - Secondary optical signal telemetry (2D FFT, YCrCb, HSV glare, temporal variance).

2. **What must be preserved:**
   - 100% of Modules 1–3 logic, tests, and API routes.
   - Zero-fake-biometrics rule: no `random()`, no hardcoded `0.94`, no simulated successes.
   - Privacy architecture: zero persistent storage of raw camera images or 512-D embedding vectors; all biometric comparisons occur in volatile memory.
   - Frontend state structure, immigration workstation aesthetic, and neutral initial states (`--`).
   - Secondary optical PAD telemetry (clearly marked as secondary indicators).

3. **What must be replaced:**
   - Replace MobileNetV3-Small with **ArcFaceEmbeddingModel** via ONNX Runtime (`w600k_r50.onnx`), outputting normalized 512-dimensional embeddings.
   - Replace standalone heuristic PAD with **MiniFASNetPAD** via PyTorch (`2.7_80x80_MiniFASNetV2.pth`), retaining optical cues as secondary defensive telemetry.
   - Replace Haar Cascade with **YuNetFaceDetector** (`cv2.FaceDetectorYN`) as primary detector returning bounding boxes and 5 keypoints (`right_eye`, `left_eye`, `nose_tip`, `right_mouth_corner`, `left_mouth_corner`), retaining Haar Cascade only as a fallback.
   - Add standardized **5-point face alignment** transforming faces to canonical ArcFace 112x112 coordinates before embedding extraction.
   - Recalibrate face matcher for 512-D ArcFace cosine distance with configurable threshold (`FACE_MATCH_THRESHOLD = 0.40`).

4. **Dependency Conflicts with ArcFace:**
   - Installing the monolithic `insightface` package introduces dependencies that clash with Protobuf and PaddleOCR.
   - **Resolution (Option A):** Load the official `w600k_r50.onnx` ArcFace model directly through `onnxruntime==1.29.0`. This provides native 512-D embeddings without any dependency conflicts.

5. **Dependency Conflicts with MiniFASNet:**
   - MiniFASNet is pure PyTorch (`torch.nn.Module`). It runs cleanly on the existing `torch==2.12.1+cpu` environment with zero new packages required.

6. **Safety of ONNX Runtime:**
   - Verified. ONNX Runtime 1.29.0 is already present and stable with CPU execution provider.

7. **PyTorch & PaddleOCR Coexistence:**
   - Verified. Setting `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python` ensures both operate without segmentation faults or descriptor errors.

8. **Model Weights Availability:**
   - All 4 verified model files are downloaded and locally validated in `backend/app/models_weights/`.

9. **External Downloads:**
   - Complete. No active network connections are required at runtime.

10. **Licensing:**
    - OpenCV YuNet: Apache 2.0.
    - MiniFASNet: Apache 2.0.
    - InsightFace ArcFace: Academic/Research non-commercial; suitable for development and demonstration of this border screening system.

---

## 3. Redesign Architecture Plan

```
DOCUMENT FACE                      LIVE CAMERA
      │                                 │
YuNet Face Detector               YuNet Face Detector
(with Haar fallback)              (with Haar fallback)
      │                                 │
0 / 1 / >1 Faces Check            0 / 1 / >1 Faces Check
      │                                 │
5-Point Landmark Extraction       5-Point Landmark Extraction
      │                                 │
Face Quality Gate                 Face Quality Gate
      │                                 │
ArcFace 112x112 Alignment         MiniFASNet PAD (Primary)
      │                           + Multi-Cue Optical Telemetry (Secondary)
ArcFace ONNX Inference                  │
(512-D L2 Normalized)             ArcFace 112x112 Alignment
      │                                 │
      │                           ArcFace ONNX Inference
      │                           (512-D L2 Normalized)
      │                                 │
      └──────────────┬──────────────────┘
                     │
         Cosine Similarity Matching
                     │
         Biometric Decision Logic
```

Proceeding to Step 1 & Step 2 implementation.
