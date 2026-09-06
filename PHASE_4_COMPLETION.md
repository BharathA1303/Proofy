# Phase 4 Completion Report: Biometric Face Verification & Anti-Spoofing Architecture

**Project:** Autonomous AI-Powered Fake Identity & Document Screening System  
**Pipeline Stage:** Module 4 — Face Verification + Presentation Attack Detection (PAD)  
**Status:** COMPLETE, AUDITED, & FULLY VERIFIED (203/203 Tests Passing)  
**Date:** September 2026  

---

## Executive Summary

Phase 4 has undergone a **complete architectural redesign and re-implementation**, replacing heuristic and surrogate prototypes with production-grade deep biometric models while strictly safeguarding interoperability with existing Modules 1–3 (Ingestion, OCR, Document Validation, and Forensic Analysis).

### Key Architectural Upgrades:
1. **Primary Face Embedding Model:** InsightFace ArcFace ResNet-50 (`w600k_r50.onnx`), extracting canonical **512-dimensional L2-normalized unit embeddings** via ONNX Runtime CPU.
2. **Primary Presentation Attack Detection (PAD):** Pretrained deep neural network **MiniFASNetV2** (`2.7_80x80_MiniFASNetV2.pth`) performing deep feature-map anti-spoofing on single-frame crops and temporal burst sequences.
3. **Secondary Defensive Telemetry:** Retained multi-cue optical analysis (2D FFT moiré frequency ratio, YCrCb chromaticity clustering, HSV specular reflection, and temporal micro-variance) strictly designated as **secondary explainable defensive telemetry**, clearly distinguished from the primary deep PAD model.
4. **Deep Face Localization & 5-Point Landmark Extraction:** Deep **SCRFD-10G** (`det_10g.onnx`) with multi-scale anchor decoding and 5-point facial landmark regression (left eye, right eye, nose, left mouth corner, right mouth corner), backed by an **OpenCV Haar Cascade** defensive fallback.
5. **Deterministic 5-Point Similarity Transformation:** Standardized **`FaceAligner`** mapping raw face detections to canonical 112x112 ArcFace coordinates via partial affine transformation (`cv2.estimateAffinePartial2D`) prior to feature extraction.
6. **Strict Single-Face Rule:** Zero faces triggers `DOCUMENT_FACE_NOT_FOUND` / `NO_FACE_DETECTED`; multiple faces (>1) immediately halts verification with `MULTIPLE_FACES_DETECTED`.
7. **Strict Zero Fake Biometrics Mandate:** No random numbers or synthetic percentages are ever generated. If a model fails to load, the system explicitly reports `MODEL_UNAVAILABLE` or `BIOMETRIC_INCONCLUSIVE`.
8. **PaddleOCR & Protobuf Coexistence:** Resolved Windows Protobuf v3/v4 descriptor conflict using `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python`, allowing ONNX Runtime, PyTorch CPU, and PaddleOCR to run in the same process with zero collisions.

---

## 1. Files Created & Modified

### Backend Core & Schemas (`backend/app/`):
- `backend/app/schemas/face_verification.py` — Updated Pydantic v2 schemas:
  - `DocumentFaceResult` & `LiveFaceResult`: bounding box, landmarks (5 points), detector used (`InsightFace-SCRFD-10G` or `OpenCV-Haar`), quality classification, and granular quality metrics.
  - `AntiSpoofResult`: Primary deep PAD assessment (`model="MiniFASNetV2"`, score, status `pass|suspected_spoof|inconclusive|model_unavailable`).
  - `SecondaryPADSchema`: Secondary optical defensive cues (`frequency_domain_score`, `color_texture_score`, `specular_reflection_score`, `temporal_variance_score`, and telemetry notes).
  - `FaceMatchResult`: `similarity` ($\in [-1.0, 1.0]$), `threshold` ($0.40$), `status`, `embedding_model="ArcFace-w600k_r50"`, `embedding_dimension=512`.
  - `FaceVerificationResponse`: Unified biometric report with decision precedence resolution.
  - `ModelInfoResponse`: Diagnostic endpoint schema reporting runtime status of all biometric engines.
- `backend/app/core/config.py`:
  - Added model asset paths: `ARCFACE_MODEL_PATH`, `SCRFD_MODEL_PATH`, `MINIFASNET_MODEL_PATH`.
  - Configured calibrated operational thresholds: `FACE_MATCH_THRESHOLD = 0.40`, `ANTI_SPOOF_THRESHOLD = 0.70`.
  - Configured Protobuf runtime compatibility: `os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")`.

### Biometric Services Engine (`backend/app/services/face/`):
- `detector_interface.py` — `FaceDetector` abstract base class and `FaceDetectionResult` dataclass with 5-point facial landmarks.
- `scrfd_detector.py` — `SCRFDDetector`: High-precision deep face detector running `det_10g.onnx` via ONNX Runtime CPU. Decodes multi-scale feature strides (8, 16, 32), bounding boxes, confidence scores, and 5 facial keypoints with NMS.
- `haar_detector.py` — `OpenCVHaarDetector`: Deterministic defensive fallback detector with synthetic landmark approximation.
- `face_detector.py` — Composite `FaceDetector` orchestrating SCRFD detection with automatic Haar cascade fallback.
- `face_aligner.py` — `FaceAligner`: 5-point landmark similarity transformation to canonical 112x112 ArcFace space using Umeyama-style partial affine mapping (`cv2.estimateAffinePartial2D`).
- `embedding_interface.py` — `FaceEmbeddingModel` abstract base class.
- `arcface_embedding.py` — `ArcFaceEmbeddingModel`: InsightFace Buffalo_L ResNet-50 ArcFace model running `w600k_r50.onnx` via ONNX Runtime CPU, producing 512-D L2-normalized unit embeddings.
- `pad_interface.py` — `PresentationAttackDetector` abstract interface and `PADAssessment` dataclass.
- `minifasnet_model.py` — Pure PyTorch architecture matching Minivision Silent-Face-Anti-Spoofing checkpoint topology (Conv_block, DepthWise, Residual blocks, and Multi-FT auxiliary classification head).
- `minifasnet_pad.py` — `MiniFASNetPAD`: Loads `2.7_80x80_MiniFASNetV2.pth` weights (334/334 matching parameters), performs 2.7x face cropping and normalization to 80x80, executes PyTorch CPU forward pass, and aggregates multi-frame bursts.
- `secondary_pad.py` — `SecondaryOpticalPAD`: Non-deep explainable optical telemetry analyzing 2D FFT moiré patterns, YCrCb chromaticity clustering, HSV specular reflection, and temporal micro-variance.
- `face_matcher.py` — `FaceMatcher`: Cosine similarity calculation service for unit vectors with strict dimension validation (512-D).
- `face_verification_service.py` — `FaceVerificationService`: End-to-end coordinator managing detection, quality gating, primary PAD, secondary optical telemetry, alignment, embedding extraction, and decision resolution.
- `session_store.py` — Thread-safe, in-memory sliding-TTL cache for original passport images during verification sessions.
- `__init__.py` — Clean module exports.

### API & Routes (`backend/app/api/v1/`):
- `backend/app/api/v1/verification.py`:
  - Added `GET /api/v1/verification/face/models` diagnostic endpoint exposing real model availability, threshold configuration, and embedding dimensionality.
  - Enhanced `POST /api/v1/verification/face` supporting multipart form data with session caching and direct document fallback.

### Frontend Workstation (`src/`):
- `src/state/verification/initialState.js`: Updated biometric state with `secondaryPad` telemetry and initial `0.40` threshold.
- `src/components/biometric/BiometricStatus.jsx` & `BiometricStatus.module.css`:
  - Professional workstation interface with manual camera trigger.
  - Live framing viewfinder with biometric guide oval.
  - Dedicated telemetry cards for Facial Vector Match (ArcFace 512-D) and Anti-Spoof (MiniFASNetV2).
  - Secondary Optical Telemetry panel displaying 2D FFT Moiré, Chroma/Texture, Specular Glare, and Temporal Micro-Variance scores.
- `src/components/verification/VerificationChecks.jsx`:
  - Biometric inspection drawer detailing Document Face Quality, Live Capture Quality, MiniFASNetV2 Liveness Score, ArcFace Cosine Match, and Secondary Optical Defense tokens.

---

## 2. Models Acquired & Deployed Locally

All model weights reside locally in `backend/app/models_weights/` and execute on CPU:

| Model Role | File Name | Size | Architecture | Input Shape | Output |
|---|---|---|---|---|---|
| **Deep Face Detector** | `det_10g.onnx` | 16.9 MB | SCRFD-10G (InsightFace Buffalo_L) | Dynamic (640x640) | Bboxes + 5 Landmarks |
| **Face Embedding** | `w600k_r50.onnx` | 174 MB | ArcFace ResNet-50 (InsightFace Buffalo_L) | `(1, 3, 112, 112)` | 512-D L2-Normalized Vector |
| **Primary Deep PAD** | `2.7_80x80_MiniFASNetV2.pth` | 1.85 MB | MiniFASNetV2 (Minivision) | `(1, 3, 80, 80)` | Liveness Probability $\in [0.0, 1.0]$ |
| **Fallback Face Detector** | OpenCV Haar Cascade | Built-in | Frontal Face Haar Wavelets | Dynamic grayscale | Bboxes |

---

## 3. Facial Landmark Alignment Pipeline

Raw face crops exhibit variable pose, roll, pitch, and scale that can distort cosine similarity comparisons. The Phase 4 pipeline enforces canonical geometric normalization via **`FaceAligner`**:

```
[Raw Bounding Box + 5 Landmarks]
  (Left Eye, Right Eye, Nose, Left Mouth, Right Mouth)
                 ↓
[Estimate Partial Affine Transformation (cv2.estimateAffinePartial2D)]
  Maps detected landmarks to canonical ArcFace template (112x112)
                 ↓
[Warp Affine with Bilinear Interpolation]
                 ↓
[Standardized 112x112 ArcFace Crop]
```

### Canonical ArcFace 112x112 Reference Coordinates:
- **Left Eye:** `(38.2946, 51.6963)`
- **Right Eye:** `(73.5318, 51.5014)`
- **Nose:** `(56.0252, 71.7366)`
- **Left Mouth:** `(41.5493, 92.3655)`
- **Right Mouth:** `(70.7299, 92.2041)`

If landmark detection is degraded, `FaceAligner` falls back to a centered, aspect-ratio-preserved bounding box crop with reflection padding to guarantee the 112x112 geometry required by ArcFace.

---

## 4. Presentation Attack Detection (PAD) Dual-Tier Design

To achieve both **state-of-the-art liveness classification** and **transparent explainability** for border officers, Phase 4 utilizes a dual-tier PAD architecture:

```
                          Live Camera Capture (Primary + Burst Frames)
                                               │
                       ┌───────────────────────┴───────────────────────┐
                       ▼                                               ▼
            [Primary Deep PAD]                             [Secondary Optical PAD]
               MiniFASNetV2                                Multi-Cue Defensive Telemetry
         (2.7x scale crop to 80x80)                                    │
                       │                              ┌────────────────┼────────────────┐
                       │                              ▼                ▼                ▼
                       │                          [2D FFT]         [YCrCb]            [HSV]
                       │                         Screen Moiré   Skin Chromaticity  Specular Glare
                       │                              │                │                │
                       ▼                              └────────────────┼────────────────┘
            Deep Liveness Score                                        ▼
             (Decision Weight)                             Secondary Optical Scores
                                                           (Explainable Telemetry)
```

1. **Primary Deep Model (`MiniFASNetV2`):**
   - Operates on a 2.7x expanded facial crop resized to 80x80 pixels.
   - Evaluates multi-layer convolutional feature representations trained specifically on 2D paper attacks, digital screen replay attacks, and mask presentations.
   - Threshold: `ANTI_SPOOF_THRESHOLD = 0.70`.
2. **Secondary Optical Telemetry (`SecondaryOpticalPAD`):**
   - **2D FFT High-Frequency Analysis:** Identifies periodic spikes created by OLED/LCD pixel grids and halftone print screening.
   - **YCrCb Chromaticity Variance:** Detects color distribution collapse characteristic of non-biological photographic prints.
   - **HSV Specular Glare:** Detects localized reflections from protective glass or photo lamination.
   - **Temporal Micro-Variance:** Analyzes frame-to-frame pixel differences across 120ms burst captures to detect static presentation attacks.

---

## 5. Decision Precedence Hierarchy

The biometric verification service executes checks in strict sequence, short-circuiting on safety violations:

```
Step 1: Document Face Detection
        ├── 0 faces detected  ──> DOCUMENT_FACE_NOT_FOUND
        └── >1 faces detected ──> MULTIPLE_FACES_DETECTED

Step 2: Live Face Detection
        ├── 0 faces detected  ──> LIVE_FACE_NOT_FOUND
        └── >1 faces detected ──> MULTIPLE_FACES_DETECTED

Step 3: Quality Gate Analysis (Sharpness, Brightness, Contrast, Size)
        └── Quality check fails ──> POOR_QUALITY / BIOMETRIC_INCONCLUSIVE

Step 4: Primary Anti-Spoofing (MiniFASNetV2)
        ├── Model unavailable ──> MODEL_UNAVAILABLE / INCONCLUSIVE
        └── Score < 0.70      ──> SUSPECTED_SPOOF (Feature matching aborted)

Step 5: Canonical Alignment (112x112 ArcFace coordinates)

Step 6: ArcFace Embedding Extraction (512-D L2-Normalized Vectors)

Step 7: Cosine Similarity Matching
        ├── Similarity >= 0.40 ──> FACE_MATCH
        └── Similarity < 0.40  ──> FACE_MISMATCH
```

---

## 6. Threshold Configuration & Operating Point Justification

Defined in `backend/app/core/config.py`:

| Parameter | Default Value | Technical Rationale |
|---|---|---|
| `FACE_MATCH_THRESHOLD` | `0.40` | Standard 1:1 operational cosine similarity verification threshold for ArcFace ResNet-50. Corresponds to approximately $10^{-4}$ False Accept Rate (FAR) under standard ICAO/NIST evaluation benchmarks. Requires cohort-specific empirical calibration in production. |
| `ANTI_SPOOF_THRESHOLD` | `0.70` | MiniFASNetV2 live classification threshold. Scores $\ge 0.70$ represent genuine presentations; scores $< 0.70$ are flagged as `SUSPECTED_SPOOF`. |
| `FACE_MIN_SIZE` | `80` pixels | Minimum facial bounding box dimension. Images smaller than 80px lack sufficient high-frequency spatial resolution for reliable 5-point landmark localization. |
| `FACE_MIN_LAPLACIAN_VAR` | `50.0` | Laplacian variance threshold. Lower values signify optical defocus or high-speed motion blur. |
| `FACE_MIN_BRIGHTNESS` | `40.0` | Minimum mean grayscale luminance (prevents severe underexposure). |
| `FACE_MAX_BRIGHTNESS` | `220.0` | Maximum mean grayscale luminance (prevents sensor saturation/washout). |
| `FACE_MIN_CONTRAST` | `25.0` | Minimum standard deviation of pixel intensities (prevents flat, low-contrast captures). |
| `SESSION_DOCUMENT_TTL_SECONDS`| `900` sec | 15-minute sliding TTL for in-memory session documents, ensuring zero disk persistence of biometric imagery. |

---

## 7. Complete Test Suite Results

The automated test suite covers all components with **203 passing tests** and **0 failures/errors**:

```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-8.4.1
rootdir: D:\PROJECTS\SIH\Product\backend
collected 203 items

tests/test_anti_spoof.py .........................                       [ 12%]
tests/test_arcface_embedding.py ....                                    [ 14%]
tests/test_document_ingestion.py .................                      [ 23%]
tests/test_face_aligner.py ...                                          [ 24%]
tests/test_face_api.py ..........                                       [ 29%]
tests/test_face_detector.py ......                                      [ 32%]
tests/test_face_matcher.py ......                                       [ 35%]
tests/test_face_quality.py ......                                       [ 38%]
tests/test_face_verification_service.py ..........                      [ 43%]
tests/test_minifasnet_pad.py ....                                       [ 45%]
tests/test_mrz_parser.py ..................................             [ 62%]
tests/test_passport_parser.py ...................................       [ 79%]
tests/test_passport_validation_service.py ............................   [ 93%]
tests/test_tampering_analysis_service.py ..............                 [100%]

============================ 203 passed in 25.62s =============================
```

### Breakdown of Biometric Tests (Phase 4):
- `tests/test_arcface_embedding.py` (4 tests): Verifies 512-dimensional vector output, strict L2 unit normalization ($\|e\|_2 \approx 1.0$), non-zero representation, and deterministic inference.
- `tests/test_minifasnet_pad.py` (4 tests): Evaluates MiniFASNet model loading, forward tensor shapes, single-frame liveness classification, and multi-frame burst scoring.
- `tests/test_face_aligner.py` (3 tests): Tests 5-point similarity transformation to canonical 112x112 ArcFace landmarks, bounding box fallback on missing landmarks, and boundary clamping.
- `tests/test_face_detector.py` (6 tests): Validates SCRFD deep detector and Haar fallback on zero faces, single face, multiple faces, context margin padding, and corrupt inputs.
- `tests/test_face_matcher.py` (6 tests): Verifies cosine matching on identical, orthogonal, opposite vectors, threshold boundaries, and dimension mismatch defenses.
- `tests/test_face_quality.py` (6 tests): Asserts blur, darkness, overexposure, small dimension, and extreme aspect ratio rejections.
- `tests/test_anti_spoof.py` (5 tests): Tests secondary optical cues (2D FFT moiré, YCrCb chroma, HSV glare, and temporal micro-variance).
- `tests/test_face_verification_service.py` (10 tests): Evaluates end-to-end orchestration (matching face pairs, mismatch face pairs, spoof intercept, missing document portrait, missing live face, multi-face abort, low quality, model unavailable resilience).
- `tests/test_face_api.py` (10 tests): Integrates `GET /api/v1/verification/face/models` diagnostic endpoint and `POST /api/v1/verification/face` multipart transactions.

---

## 8. Frontend Quality & Production Build

- **Linter:** `oxlint`
  - Result: **0 warnings and 0 errors** (24 files checked, 104 rules).
- **Bundler:** Vite v8.2.2
  - Result: **Production bundle compiled cleanly in 344ms**.
  - Output Assets:
    - `dist/index.html`: `0.94 kB`
    - `dist/assets/index-XdYTSggM.css`: `48.96 kB`
    - `dist/assets/index-CSzeQHkU.js`: `354.95 kB`

---

## 9. Biometric Privacy, Ethics & Operational Constraints

1. **Transient Memory Processing:** Biometric face embeddings and live camera frames exist only in volatile RAM during active pipeline execution. Vectors and raw facial crops are **never written to persistent disk**, logged to files, or leaked in user-facing JSON payloads.
2. **Camera Hardware Control:** Camera streams are initiated solely upon explicit border officer button interaction (`Start Face Verification`). All hardware tracks (`track.stop()`) are immediately terminated upon capture completion or dialog dismissal.
3. **Threshold Transparency:** Thresholds (`0.40` for ArcFace, `0.70` for MiniFASNet) are explicitly surfaced in the operator interface alongside raw scores so officers never face opaque "black-box" decisions.
4. **No Unauthorized Clearance:** Module 4 outputs `FACE_MATCH`, `FACE_MISMATCH`, or `SUSPECTED_SPOOF`. It **never** issues final border clearance decisions (such as "AUTHENTICATED" or "PASSPORT IS GENUINE"), which are strictly reserved for later modules (Registry Verification and Risk Engine).
5. **Operational Calibration Required:** Before deployment at a national border checkpoint, the ArcFace cosine similarity threshold and MiniFASNet liveness cutoff must be empirically calibrated using checkpoint-specific camera hardware and demographic cohorts to ensure FAR and FRR meet national border control standards.
