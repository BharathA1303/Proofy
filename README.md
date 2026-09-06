# AI-Based Fake Identity & Document Screening System

**Smart India Hackathon (SIH)**  
**Version:** `1.0.0-phase12` (Final Production Prototype)  
**Status:** All 12 Phases Completed · 695 Tests Passing · 0 Failures  

---

> [!IMPORTANT]  
> **Operational Governance Mandate:** This software is an **AI-assisted decision support platform** designed to augment authorized border control and customs officers. Automated risk scores and system recommendations are strictly advisory. The software **never** autonomously grants admission or denies entry; all final determinations are executed by authorized human officers.

---

## 1. Supported Document Profiles

The system implements a generic, document-agnostic verification architecture supporting five credential categories:

1. **Passport:** International TD3 standard (MRZ extraction, optical checksum validation, ghost photo inspection, localized ELA forensics).
2. **Visa:** ICAO Doc 9303 MRVA/B standard with strict passport identifier binding.
3. **Driving License:** Regional layout with optical token extraction, microprint inspection, and registry sandbox comparison.
4. **National ID:** Controlled bilingual Aadhaar reference profile with secure 2D QR decoding and token-set name comparison.
5. **Border Permit:** Multi-field cross-border entry permit with permit serial binding and security stamp inspection.

---

## 2. Core Screening Pipeline

```
Document Upload
      ↓
M1 — Extraction / OCR (PaddleOCR + Regex + MRZ Parsers)
      ↓
M2 — Document Validation (ICAO Checksums, Expiry, Date Chronologies)
      ↓
M3 — Tampering & Forensic Analysis (ELA, Compression Analysis, Photo Boundary)
      ↓
M4 — Biometrics & PAD (SCRFD Detection + ArcFace Embeddings + MiniFASNet Spoof Guard)
      ↓
M5 — Registry Verification (Sandbox Database Provider Comparison)
      ↓
M6 — Composite Risk Engine (Evidence Aggregation + Conflict Detection)
      ↓
Cross-Document Intelligence (Multi-Doc Case Consistency Engine)
      ↓
Officer Decision Support Station (Authoritative Human Action)
      ↓
Blockchain Immutable Audit Ledger (Zero PII · Canonical SHA-256 Hashing)
```

---

## 3. Blockchain & Evidence Integrity Layer

- **Zero Sensitive Data On-Chain:** Biometric embeddings, document scans, facial crops, and raw OCR text are **never** stored on the blockchain.
- **Canonical Evidence Hashing:** The system converts multi-module findings into a deterministic JSON representation and computes a SHA-256 digest.
- **Tamper Detection:** The platform provides one-click cryptographic integrity verification (`/api/v1/audit/{target_id}/verify`). If any stored evidence or database field is modified offline, the recalculation detects the hash divergence and triggers an `INTEGRITY_FAILURE` alert.
- **Human-in-the-Loop Anchoring:** Every authoritative officer decision (`CLEAR_ADMIT`, `REFER_TO_SECONDARY`, `REFUSE_ENTRY`, `REQUEST_ADDITIONAL_DOCUMENTS`) is permanently anchored to the chain.

---

## 4. Documentation Suite

- [System Architecture](file:///docs/ARCHITECTURE.md) — Comprehensive technical architecture, data flows, and module contracts.
- [API Reference](file:///docs/API.md) — Complete endpoint inventory with request/response schemas.
- [Security & Privacy](file:///docs/SECURITY.md) — File security, decompression bomb limits, and PII quarantine.
- [Deployment Guide](file:///docs/DEPLOYMENT.md) — Hardware prerequisites, model setup, and service launch.
- [SIH Demonstration Guide](file:///docs/DEMO.md) — Step-by-step evaluation guide for Scenarios A, B, C, D, and E.
- [Limitations & Disclaimers](file:///docs/LIMITATIONS.md) — Boundaries, edge cases, and ethical AI anti-profiling policies.

---

## 5. Quick Start

### Backend (FastAPI + ONNXRuntime + PaddleOCR)
```bash
cd backend
python -m venv venv
venv\Scripts\activate      # On Windows
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend (React + Vite + Light Enterprise UI)
```bash
npm install
npm run lint               # 0 errors, 0 warnings
npm run dev                # Serves at http://localhost:5173
```

---

## 6. Test Suite & Verification Results

```bash
cd backend
python -m pytest tests/ -v
# ============================ 695 passed in 59.20s ============================
```
- **Total Unit & Integration Tests:** 695
- **Regressions:** 0
- **SIH Demonstration Scenarios (A, B, C, D, E):** 100% Passing
- **Frontend Oxlint:** 0 errors, 0 warnings
- **Vite Production Build:** SUCCESS (0.4s)
