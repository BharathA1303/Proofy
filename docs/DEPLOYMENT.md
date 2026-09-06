# Deployment & Operations Guide

**Platform:** AI-Based Fake Identity & Document Screening System  
**Version:** `1.0.0-phase12`  
**Environment:** Demonstration / Evaluation Sandbox  

---

## 1. System Requirements

### Hardware
- **CPU:** 4 physical cores minimum (x86_64 or ARM64)
- **RAM:** 8 GB minimum (16 GB recommended for concurrent OCR and deep face inference)
- **Storage:** 5 GB free SSD storage (for model weights, ONNX runtimes, and local ledger)

### Software
- **Python:** 3.11+
- **Node.js:** 18+ (LTS)
- **Operating Systems:** Windows 10/11, Ubuntu 22.04 LTS, macOS 13+

---

## 2. Model Weights Verification

Ensure the pre-trained weights exist in `backend/app/models_weights/`:
1. `w600k_r50.onnx` (ArcFace ResNet-50 face embedding model, ~170MB)
2. `det_10g.onnx` (SCRFD deep face detector, ~16MB)
3. `2.7_80x80_MiniFASNetV2.pth` (MiniFASNet presentation attack detection, ~1.2MB)

---

## 3. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create and activate Python virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run startup verification & diagnostics
python -c "from app.main import app; print('App loaded successfully, version:', app.version)"

# Launch FastAPI development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 4. Frontend Setup

```bash
# From the project root directory
npm install

# Run Oxlint validation
npm run lint

# Launch Vite development server
npm run dev
# Terminal will serve on http://localhost:5173
```

---

## 5. Verifying Operational Health

Check that all subsystems and models are active:

```bash
# High-level system health
curl -s http://localhost:8000/api/v1/system/health | jq .

# Deep model inspection
curl -s http://localhost:8000/api/v1/system/diagnostics | jq .
```

Expected response confirms:
- `"status": "HEALTHY"`
- `"all_models_ready": true`
- `"chain_valid": true`
- `"environment": "demonstration"`
