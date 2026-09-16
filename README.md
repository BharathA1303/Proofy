# Meiyari — AI-Based Fake Identity & Document Screening System

**Smart India Hackathon (SIH) Project**
**Product name:** Meiyari (frontend `APP_VERSION = 2.0`) · **Backend API version:** `1.0.0-phase12`
**Test suite:** 1060+ backend tests passing (`cd backend && python -m pytest tests/ -q`)

> [!IMPORTANT]
> **Operational Governance Mandate.** This software is an **AI-assisted decision-support platform** for authorized border control, customs, and identity-verification officers. All automated risk scores, forensic flags, and registry comparisons are strictly **advisory**. The system **never** autonomously admits, denies, deports, or otherwise adjudicates a traveler. Every legally binding action (`CLEAR_ADMIT`, `REFER_TO_SECONDARY`, `REFUSE_ENTRY`, `REQUEST_ADDITIONAL_DOCUMENTS`) is recorded as the explicit act of an authenticated human officer.

This document is written to be a **complete, standalone reference** — a human or an AI agent should be able to understand the entire system's purpose, architecture, data flow, module boundaries, and how to run/extend it, from this file alone.

---

## Table of Contents

1. [What This Project Is](#1-what-this-project-is)
2. [Repository Layout](#2-repository-layout)
3. [System Architecture](#3-system-architecture)
4. [Supported Document Profiles](#4-supported-document-profiles)
5. [Backend: Module-by-Module Pipeline (M1–M6)](#5-backend-module-by-module-pipeline-m1m6)
6. [Cross-Document Intelligence & Case Model](#6-cross-document-intelligence--case-model)
7. [Blockchain / Immutable Audit Ledger](#7-blockchain--immutable-audit-ledger)
8. [Backend Codebase Map](#8-backend-codebase-map)
9. [Frontend Architecture](#9-frontend-architecture)
10. [Authentication & MFA (Frontend, Demo-Grade)](#10-authentication--mfa-frontend-demo-grade)
11. [API Surface Summary](#11-api-surface-summary)
12. [Configuration Reference](#12-configuration-reference)
13. [Getting Started](#13-getting-started)
14. [Testing](#14-testing)
15. [Security & Privacy Posture](#15-security--privacy-posture)
16. [Known Limitations](#16-known-limitations)
17. [Full Documentation Index](#17-full-documentation-index)

---

## 1. What This Project Is

Meiyari screens identity and travel documents (passports, visas, driving licenses, national ID cards, border permits) for **forgery, tampering, and identity mismatch**, and produces an explainable, evidence-backed risk report for a human officer to act on. It combines:

- **OCR + structured document parsing** (PaddleOCR, regex/MRZ/QR parsers per document type)
- **Document validation** (ICAO checksums, expiry/date chronology, structural field checks)
- **Digital image forensics** (Error Level Analysis, compression-artifact analysis, photo-boundary/splice detection, metadata inspection)
- **Biometric face verification + liveness/anti-spoofing** (SCRFD face detection, ArcFace embeddings, MiniFASNetV2 presentation-attack detection)
- **Registry cross-checks** against a sandboxed/mock "government registry" database
- **Cross-document consistency checking** when multiple documents belong to one case (e.g., passport + visa)
- **A composite, explainable risk engine** that aggregates all of the above into a single advisory score/level
- **A tamper-evident blockchain-style audit ledger** that hash-chains every pipeline milestone and every officer decision, without ever storing biometric data, document images, or PII on-chain

The system is explicitly a **decision-support tool**, not an enforcement system — this constraint is enforced architecturally (the pipeline's terminal automated state is `COMPLETED`, never an admit/deny verdict) and is repeated throughout the codebase and docs.

---

## 2. Repository Layout

```
Product/
├── backend/                      # FastAPI + Python ML/CV backend
│   ├── app/
│   │   ├── main.py               # FastAPI app factory, lifespan/startup, router mounting
│   │   ├── core/                 # Settings (config.py) and exception handlers
│   │   ├── api/v1/                # HTTP route handlers (verification, cases, audit, documents, system)
│   │   ├── schemas/               # Pydantic request/response models (12 schema modules, 80+ classes)
│   │   ├── services/               # All business logic — see §8 for the full map
│   │   ├── data/                   # Runtime data: blockchain ledger JSON, encrypted registry DB
│   │   └── models_weights/         # ONNX / PyTorch model weight files (SCRFD, ArcFace, MiniFASNetV2)
│   ├── tests/                     # 1060+ pytest tests (unit + integration + scenario tests)
│   ├── requirements.txt
│   └── pyproject.toml
├── src/                           # React 19 + Vite frontend ("Meiyari")
│   ├── App.jsx                    # Router root: /login, /register, / (protected)
│   ├── pages/                     # VerificationPage (main workspace), auth pages
│   ├── components/                 # UI components grouped by domain — see §9
│   ├── state/                      # React Context state: auth/ and verification/
│   ├── services/                    # Axios/fetch API clients (verificationApi, caseApi, auditApi, useOCRSubmit)
│   ├── config/                      # appConfig.js (branding, API base URL, feature flags), documentProfiles.js
│   └── utils/totp.js                # Client-side RFC 6238 TOTP implementation for MFA demo
├── public/                        # Static assets + sample document images per document type
├── docs/                          # Deep-dive documentation (architecture, API, security, deployment, demo, per-phase notes)
├── PHASE_4_AUDIT_REPORT.md, PHASE_4_COMPLETION.md, PHASE_5_REGISTRY.md   # Historical phase build logs
├── package.json                   # Frontend deps/scripts (Vite, React 19, react-router-dom, axios, qrcode)
└── vite.config.js                 # Dev server on port 4000, proxies /api → http://localhost:9000
```

---

## 3. System Architecture

```
┌───────────────────────────────────────────────────────────────────────────┐
│                         TRAVELER DOCUMENT UPLOAD                           │
│                    (React frontend — camera or file upload)               │
└───────────────────────────────────┬───────────────────────────────────────┘
                                     │  multipart/form-data
                                     ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                     GENERIC DOCUMENT PIPELINE (per document)              │
│                                                                             │
│   M1  Extraction / OCR      PaddleOCR + regex + MRZ/QR parsers            │
│         │                                                                  │
│   M2  Document Validation    ICAO checksums, expiry, date chronology      │
│         │                                                                  │
│   M3  Forensics & Tampering  ELA, compression analysis, photo boundary,   │
│         │                    metadata inspection, stamp/microprint checks │
│   M4  Biometrics & PAD       SCRFD detect → ArcFace embed → MiniFASNetV2  │
│         │                    liveness/spoof guard → 1:1 face match        │
│   M5  Registry Verification  Adapter → mock/sandbox provider → comparator │
└───────────────────────────────────┬───────────────────────────────────────┘
                                     ▼
┌───────────────────────────────────────────────────────────────────────────┐
│         CROSS-DOCUMENT INTELLIGENCE (multi-document case engine)          │
│   Compares identifiers/fields across documents in the same case           │
│   (e.g., passport_number binding between Passport ↔ Visa)                 │
└───────────────────────────────────┬───────────────────────────────────────┘
                                     ▼
┌───────────────────────────────────────────────────────────────────────────┐
│   M6  COMPOSITE RISK ENGINE — evidence aggregation, conflict detection,   │
│        weighted scoring → LOW / MEDIUM / HIGH / CRITICAL (advisory only)  │
└───────────────────────────────────┬───────────────────────────────────────┘
                                     ▼
┌───────────────────────────────────────────────────────────────────────────┐
│            OFFICER DECISION SUPPORT STATION (authoritative human)        │
│   CLEAR_ADMIT · REFER_TO_SECONDARY · REFUSE_ENTRY ·                       │
│   REQUEST_ADDITIONAL_DOCUMENTS                                            │
└───────────────────────────────────┬───────────────────────────────────────┘
                                     ▼
┌───────────────────────────────────────────────────────────────────────────┐
│      BLOCKCHAIN IMMUTABLE AUDIT LEDGER — zero PII, canonical SHA-256      │
│      hash-chain of every milestone + the final officer decision           │
└───────────────────────────────────────────────────────────────────────────┘
```

### Verification Orchestrator — 11-stage lifecycle

Every verification request moves through `VerificationOrchestrator` (`backend/app/services/orchestrator/`), which tracks state, timestamps, and correlation IDs across:

```
STANDBY → DOCUMENT_SELECTED → UPLOADING → OCR_PROCESSING → VALIDATING →
FORENSICS → BIOMETRIC_PENDING → BIOMETRIC_PROCESSING → REGISTRY_VERIFICATION →
RISK_ASSESSMENT → OFFICER_REVIEW → COMPLETED
```

- **Correlation IDs:** every request gets a UUID traced through logs across all modules.
- **Stage benchmarking:** start/end timestamps recorded per stage (exposed via `GET /api/v1/system/benchmarks`).
- **Fault tolerance:** if the blockchain ledger or a registry provider is unreachable, the core pipeline still completes; audit events queue as `PENDING` instead of blocking or dropping evidence.

### Normalized Evidence Model

Every module, cross-document relation, and officer action emits a `NormalizedEvidenceItem` — a uniform evidence unit so the risk engine and audit ledger never need module-specific logic:

```json
{
  "evidence_id": "EV-9A8B7C6D",
  "case_id": "CASE-2026-001",
  "document_id": "DOC-PASSPORT-01",
  "document_type": "passport",
  "module": "forensics",
  "signal_type": "ela_compression_anomaly",
  "status": "suspicious",
  "severity": "high",
  "confidence": 0.88,
  "description": "Error Level Analysis detected localized compression discontinuity in photo patch",
  "source": "Forensic ELA Engine v3.0",
  "timestamp": 1788700000.0,
  "module_version": "1.0.0",
  "model_version": null,
  "provenance": { "box": [120, 45, 300, 260] }
}
```

`EvidencePackage` groups all evidence for a session/case and exposes `to_canonical_dict()` — a deterministic, lexicographically-sorted representation used as the input to the SHA-256 hash anchored on the blockchain.

---

## 4. Supported Document Profiles

The platform is **document-agnostic**: rather than hardcoding a pipeline per document, every credential type is a declarative `DocumentProfile` registered in `DocumentProfileRegistry` (`backend/app/services/documents/profiles/document_profile_registry.py`). Each profile declares its own extraction adapter, validation rules, forensic expectations, and registry provider — the M1–M5 pipeline stages are generic and simply dispatch to whichever profile matches the upload.

| Profile Key | Document | Standard / Layout | Key Security Signals | Registry Provider |
|---|---|---|---|---|
| `passport` | International Passport | ICAO Doc 9303 TD3 (MRZ) | Optical checksum, ghost photo, ELA | `mock_passport.py` |
| `visa` | Travel Visa | ICAO Doc 9303 MRV-A/B | MRZ, passport-number binding | `mock_visa.py` |
| `driving_license` | Driving License | Regional DL layout | Microprint, photo boundary | `mock_driving_license.py` |
| `national_id` | National ID (Aadhaar-style reference) | Bilingual layout + 2D secure QR | QR payload validation, token-set name match | `mock_national_id.py` |
| `border_permit` | Cross-Border Entry Permit | Fixed multi-field permit format | Permit serial, security stamp | `mock_border_permit.py` |
| `voter_id` | Voter ID (reference profile) | Regional layout | Identifier structural check | `mock_voter_id.py` |
| `pan_card` | PAN Card (reference profile) | Fixed alphanumeric ID format | Checksum-style identifier validation | `mock_pan_card.py` |

Each `DocumentProfile` bundles:
1. **Extraction adapter** — OCR text parser, MRZ parser, or QR/barcode decoder specific to the layout.
2. **Field normalizer** — canonicalizes raw OCR text (dates, names, ID formats) before validation/comparison.
3. **Validator** — checksum algorithms (ICAO check digits, Aadhaar Verhoeff-style checks, etc.), date chronology, required-field checks.
4. **Forensic expectations** — expected photo-patch location, layout regions for ELA/tamper checks.
5. **Registry provider adapter** — maps document fields to a lookup call against the registry engine.

All of these live under `backend/app/services/documents/<document_type>/` (parser, validator, field_normalizer, and where applicable qr_validator / region_detector / identifier_validator files) and are unit-tested individually plus through shared "case scenario" and "extensibility" test suites (see `backend/tests/test_<doc>_*`).

---

## 5. Backend: Module-by-Module Pipeline (M1–M6)

| Module | Name | Core Tech | Backend Location |
|---|---|---|---|
| **M1** | Extraction / OCR | PaddleOCR, regex, MRZ/QR parsers | `services/ocr/`, `services/machine_readable/`, `services/documents/*/*_parser.py` |
| **M2** | Document Validation | ICAO checksums, expiry/date rules | `services/validation/`, `services/documents/*/*_validator.py` |
| **M3** | Forensics & Tampering | ELA, compression analysis, photo boundary, metadata, stamp detection | `services/document_forensics/`, `services/forensics/` |
| **M4** | Biometrics & PAD | SCRFD face detection, ArcFace embeddings, MiniFASNetV2 anti-spoof | `services/face/` |
| **M5** | Registry Verification | Adapter → provider → comparator against sandbox DB | `services/registry/` |
| **M6** | Composite Risk Engine | Evidence aggregation, conflict detection, weighted scoring | `services/risk/` |

Supporting cross-cutting services:
- `services/ingestion/` — file upload hardening (magic-byte checks, size limits, decompression-bomb guard).
- `services/preprocessing/` — image deskewing, normalization before OCR/forensics.
- `services/quality/` — document/image quality scoring (blur, glare, resolution) prior to running the rest of the pipeline.
- `services/document_intelligence/` — higher-level document classification/routing helpers.
- `services/evidence/` — `NormalizedEvidenceItem` / `EvidencePackage` construction and canonicalization.
- `services/audit/` — blockchain ledger interface and integrity verification (see §7).
- `services/case/` — multi-document case lifecycle (create, add/remove document, recompute relationships/risk).
- `services/orchestrator/` — the `VerificationOrchestrator` that drives the 11-stage lifecycle end-to-end.
- `services/system/` — health/diagnostics/benchmark telemetry.

### M4 detail — Biometric pipeline
1. **SCRFD** (`det_10g.onnx`) detects the face region in the document photo and in the live/webcam capture.
2. **ArcFace** (`w600k_r50.onnx`, ResNet-50 backbone) generates a 512-dimensional embedding for each detected face.
3. **MiniFASNetV2** (`2.7_80x80_MiniFASNetV2.pth`) scores the live capture for presentation-attack signals (printed photo, screen replay).
4. Cosine similarity between the two embeddings is compared against `FACE_MATCH_THRESHOLD` (default `0.30`, calibrated for cross-domain ID-photo-to-webcam matching) to produce a match/no-match verdict with confidence.
5. A Haar-cascade fallback detector exists for environments where the ONNX SCRFD model is unavailable (`FACE_DETECTOR_BACKEND=haar`).

### M5 detail — Registry verification
- `services/registry/base.py` defines the abstract provider interface; `services/registry/providers/mock_*.py` implement in-memory sandbox lookups seeded via `services/registry/db/registry_db.py` (a local **encrypted SQLite** database, see `services/registry/db/crypto.py`).
- `services/registry/adapters/*_adapter.py` map each document profile's fields to the generic provider call.
- `services/registry/comparator.py` and `normalizers.py` perform field-level comparison (name token-set matching, date/ID canonicalization) and produce match/mismatch/unavailable evidence.
- `services/registry/resolver.py` picks the correct provider mode per document type (`mock` / `sandbox` / `external`) from settings.
- Registry lookups are timeout-bounded (`REGISTRY_CONNECT_TIMEOUT`, `REGISTRY_READ_TIMEOUT`, `REGISTRY_TOTAL_TIMEOUT`) and fail **gracefully to `UNAVAILABLE`** rather than blocking the pipeline or being treated as a fraud signal — see Demo Scenario D in `docs/DEMO.md`.

### M6 detail — Risk engine
- `services/risk/` aggregates every `NormalizedEvidenceItem` (from M1–M5 and cross-document relationships) using configurable weights (`RISK_CONFIG_VERSION`) and threshold bands: `RISK_THRESHOLD_MEDIUM` (25), `RISK_THRESHOLD_HIGH` (50), `RISK_THRESHOLD_CRITICAL` (75).
- Includes a dedicated **conflict detector** that raises severity when cross-document identifier bindings mismatch (e.g., visa references a different passport number than the passport actually presented).
- Explicitly excludes demographic attributes (race, ethnicity, religion, gender, nationality, political affiliation) from scoring — see `docs/LIMITATIONS.md` §4, "Ethical AI & Anti-Profiling Invariant."

---

## 6. Cross-Document Intelligence & Case Model

A **Verification Case** (`services/case/`, schema `schemas/case.py`) groups up to `MAX_DOCUMENTS_PER_CASE` (default 10) documents belonging to one traveler/session. When two or more documents are attached:

- `services/documents/relationships/document_relationship.py` and `services/cross_document/` compare shared identifiers/fields across document types (e.g., `passport_number`, `name`, `date_of_birth`, `nationality` between a Passport and a Visa).
- Each comparison produces a relationship record: `MATCHED`, `MISMATCH`, or `UNVERIFIABLE`, feeding back into the M6 risk engine as additional evidence.
- Profile-specific cross-document logic lives under `services/cross_document/profiles/`.
- Adding, replacing, or removing a document from a case automatically invalidates and recomputes relationships and the case-level risk assessment (`DELETE /api/v1/verification/case/{case_id}/documents/{document_id}`).

---

## 7. Blockchain / Immutable Audit Ledger

**Purpose:** provide cryptographic, tamper-evident proof that evidence and officer decisions were not altered after the fact — **without ever storing sensitive data on-chain**.

### On-chain vs. off-chain separation

| Data | Off-chain (local/session) | On-chain |
|---|---|---|
| Facial photos, face crops | Ephemeral session / memory only | **Never** |
| 512-d ArcFace embeddings | Volatile memory, never serialized | **Never** |
| Document image bytes | In-memory / session disk cache | **Never** |
| Raw OCR text, name, DOB, address | Ephemeral document session | **Never** |
| Normalized evidence digest | Structured JSON | **Canonical SHA-256 hash only** |
| Officer decision + reason | Encrypted audit DB | Anchored event + hash digest |

### Hash-chain structure

```
H_0 = SHA256(Genesis Block)
H_i = SHA256(i ‖ H_{i-1} ‖ timestamp ‖ target_id ‖ event_type ‖ evidence_hash ‖ version ‖ metadata)
```

Implemented in `services/audit/` behind a `BlockchainLedger` interface:
- `append_block(target_id, event_type, evidence_hash, metadata)` — appends an immutable block.
- `verify_chain()` — recalculates the chain from genesis and confirms no block was altered.
- `get_chain(target_id)` — retrieves the block history for a case or verification ID.

### Chain-of-custody milestones (anchored automatically)
`CASE_CREATED → DOCUMENT_UPLOADED → OCR_COMPLETED → VALIDATION_COMPLETED → FORENSICS_COMPLETED → BIOMETRIC_COMPLETED → REGISTRY_COMPLETED → CROSS_DOCUMENT_EVALUATED → RISK_ASSESSMENT_COMPLETED → OFFICER_REVIEWED`

### Tamper detection in practice
`POST /api/v1/audit/{target_id}/verify` recomputes the canonical SHA-256 of the *current* stored evidence and compares it against the hash anchored at write time. Any offline modification to a stored evidence record — even a single field — produces `integrity_status: "INTEGRITY_FAILURE"`.

### Resilience
If the ledger's on-disk store (`app/data/blockchain_ledger.json`) is temporarily unavailable, `AuditIntegrityService` queues the event in an in-memory `_pending_queue` and retries automatically on recovery — a ledger outage never blocks border-screening throughput.

> ⚠️ This is a **local, permissioned SHA-256 hash-chain** for auditable demo execution — not a public/decentralized cryptocurrency network, and not connected to any real government ledger. See `docs/LIMITATIONS.md`.

---

## 8. Backend Codebase Map

```
backend/app/
├── main.py                        FastAPI factory, CORS, lifespan (OCR warmup, registry DB seed)
├── core/
│   ├── config.py                  Pydantic Settings — every tunable in one place (see §12)
│   └── exceptions.py               Central exception → HTTP response mapping
├── api/v1/
│   ├── verification.py             /verification/* — orchestrate, case create/add/remove docs
│   ├── cases.py                    Case retrieval/listing endpoints
│   ├── documents.py                 Document-scoped endpoints
│   ├── audit.py                     /audit/* — chain retrieval, integrity verify, officer decisions
│   └── system.py                    /system/* — health, diagnostics, benchmarks
├── schemas/                        Pydantic models: audit, case, cross_document, evidence,
│                                    face_verification, forensics, ocr, quality, registry, risk, validation
├── services/
│   ├── ocr/                        PaddleOCR engine wrapper (singleton, warmed up at startup)
│   ├── machine_readable/           MRZ / QR / barcode decoding helpers
│   ├── documents/                  Per-document parser/validator/normalizer + profile registry (§4)
│   ├── document_intelligence/      Document classification/routing
│   ├── validation/                 Shared M2 validation utilities
│   ├── document_forensics/         M3 forensic engines (ELA, compression, photo boundary, stamp, metadata)
│   ├── forensics/                  Shared forensic primitives/aggregator
│   ├── face/                       M4 — SCRFD detector, ArcFace embedder, MiniFASNetV2 PAD, matcher, quality gates
│   ├── registry/                   M5 — providers, adapters, comparator, resolver, encrypted sandbox DB
│   ├── cross_document/             Cross-document relationship + conflict evaluation
│   ├── risk/                       M6 — evidence aggregation, conflict detection, composite scoring
│   ├── evidence/                   NormalizedEvidenceItem / EvidencePackage canonicalization
│   ├── audit/                      Blockchain ledger + integrity verification service
│   ├── case/                       Multi-document case lifecycle management
│   ├── orchestrator/               VerificationOrchestrator — the 11-stage state machine
│   ├── ingestion/                  Upload hardening: magic bytes, size caps, decompression-bomb guard
│   ├── preprocessing/               Image deskew/normalize before OCR
│   ├── quality/                     Image/document quality scoring
│   └── system/                     Health/diagnostics/benchmark telemetry
├── data/                           blockchain_ledger.json, encrypted registry sandbox DB (gitignored at runtime)
└── models_weights/                 det_10g.onnx (SCRFD), w600k_r50.onnx (ArcFace), 2.7_80x80_MiniFASNetV2.pth
```

`backend/tests/` mirrors this structure closely — 1060+ tests including per-document parser/validator/profile/registry tests, cross-document tests, forensic-module tests, biometric tests, risk-engine tests, and end-to-end `test_sih_demo_scenarios.py` covering the walkthrough scenarios in `docs/DEMO.md`. Synthetic sample generators (`create_synthetic_*.py`, `generate_*_samples.py`) produce realistic fake documents for testing without any real PII.

---

## 9. Frontend Architecture

**Stack:** React 19, Vite 8, React Router 7, Axios, plain CSS Modules (no CSS framework). Lint via `oxlint`.

```
src/
├── main.jsx / App.jsx      Router root: /login, /register, "/" (protected, requires auth)
├── pages/
│   ├── VerificationPage.jsx        Main officer workspace (single-doc + multi-doc case modes)
│   └── auth/                       LoginPage, RegisterPage (with MFA/TOTP setup flow)
├── state/
│   ├── auth/                       AuthContext.jsx — login/register/session/MFA state (see §10)
│   └── verification/                VerificationContext + reducer — single source of truth for
│                                    the active verification/case session, driven by an action reducer
├── services/                       API clients — thin wrappers over fetch/axios:
│   ├── verificationApi.js          Single-document orchestration calls
│   ├── caseApi.js                  Multi-document case CRUD + cross-document/risk retrieval
│   ├── auditApi.js                 Blockchain chain retrieval, integrity verify, officer decision submit
│   └── useOCRSubmit.js             Hook wrapping document upload + OCR submission flow
├── components/
│   ├── upload/                     DropZone, UploadPanel — document/camera intake
│   ├── document/                   DocumentSelector, DocumentWorkspace
│   ├── verification/                 VerificationChecks, VerificationResult (M1–M2 display)
│   ├── forensic/                    ForensicEvidence (M3 display, heatmap-style overlays)
│   ├── biometric/                   BiometricStatus (M4 display)
│   ├── registry/                    RegistryStatus (M5 display)
│   ├── risk/                        RiskAssessmentPanel (M6 composite score/level display)
│   ├── case/                        Multi-doc case UI: AddDocumentModal, CaseDocuments,
│   │                                CrossDocumentPanel, CaseRiskSummary, EvidenceIntegrityPanel,
│   │                                OfficerDecisionPanel, VerificationCase (case shell)
│   ├── traveler/                    TravelerInformation (extracted identity summary)
│   ├── milestone/                   MilestoneStepper (chain-of-custody progress UI)
│   ├── workflow/                    Stage1Intake..Stage4Clearance, StageStepper (guided flow UI)
│   ├── navigation/                  SidebarDrawer
│   └── common/                      ErrorBoundary, QRCodeView, SectionHeader, StatusBadge
├── config/
│   ├── appConfig.js                 Branding (APP_NAME="Meiyari"), API_BASE_URL, feature flags
│   ├── documentProfiles.js           Frontend-side document type metadata (labels, icons, sample sets)
│   └── mockSampleOptions.js          Sample document picker options (backed by public/samples/*)
└── utils/totp.js                    RFC 6238 TOTP generator/verifier for the MFA demo (see §10)
```

### Frontend ↔ backend wiring
- Dev server: **Vite on port 4000** (`vite.config.js`), proxying `/api/*` to the FastAPI backend at `http://localhost:9000`.
- `API_BASE_URL` (in `src/config/appConfig.js`) defaults to `http://localhost:9000` and can be overridden via `VITE_API_BASE_URL` in `.env.local`.
- Feature flags (`FEATURES` in `appConfig.js`) toggle backend integration, sample-document loading, the forensic panel, and blockchain-audit UI — useful for running the frontend standalone in a demo/offline mode.

> **Note on ports:** some of the docs under `docs/` (written during earlier phases) reference `localhost:5173` (Vite default) and backend port `8000`. The current, authoritative configuration is **frontend `:4000`** and **backend `:9000`** (see `vite.config.js` and `src/config/appConfig.js`). If you see a discrepancy, trust `vite.config.js` / `appConfig.js` over prose in `docs/`.

---

## 10. Authentication & MFA (Frontend, Demo-Grade)

`src/state/auth/AuthContext.jsx` implements a **client-only** auth layer for demo/evaluation purposes:

- Username/password login against a small seed list of officer accounts (`INITIAL_USERS`), persisted to `localStorage` (`meiyari_registered_users`, `meiyari_user_session`).
- **TOTP-based MFA** (RFC 6238), implemented from scratch in `src/utils/totp.js` (Base32 secret generation, `otpauth://` URI construction for QR provisioning, and 6-digit code verification with a time-drift window) — no server-side auth exists; this is a **UI/UX and MFA-flow demonstration**, not a production identity provider.
- QR code rendering for authenticator-app enrollment uses the `qrcode` npm package (`src/components/common/QRCodeView.jsx`).
- Registration flow lets a new "officer" self-register and immediately sets up MFA.
- `ProtectedRoute` in `App.jsx` gates the `/` verification workspace behind `isAuthenticated`.

> **Do not treat this as production authentication.** Passwords are stored in plaintext in `localStorage` for demo convenience (see seed accounts in `AuthContext.jsx`). A production deployment must replace this entirely with a real identity provider / backend-issued session tokens — this is called out explicitly so no one mistakes the demo login for a security boundary.

---

## 11. API Surface Summary

**Base URL:** `http://localhost:9000/api/v1` · **Interactive docs:** `http://localhost:9000/docs` (Swagger) and `/redoc`.

| Method & Path | Purpose |
|---|---|
| `POST /verification/orchestrate` | Run the full single-document 11-stage pipeline (OCR → validation → forensics → biometrics → registry → risk). |
| `POST /verification/case` | Create a new multi-document verification case. |
| `POST /verification/case/{case_id}/documents` | Attach/replace a document on an existing case; recomputes cross-document relationships. |
| `DELETE /verification/case/{case_id}/documents/{document_id}` | Remove a document; invalidates and recomputes relationships/risk. |
| `GET /audit/{target_id}/chain` | Retrieve the full blockchain audit trail for a case or verification ID. |
| `POST /audit/{target_id}/verify` | Recompute and compare the canonical evidence hash — detects tampering. |
| `POST /audit/{target_id}/officer-decision` | Record an authoritative human decision (`CLEAR_ADMIT`, `REFER_TO_SECONDARY`, `REFUSE_ENTRY`, `REQUEST_ADDITIONAL_DOCUMENTS`) permanently to the ledger. |
| `GET /system/health` | High-level readiness (OCR engine, models, ledger). |
| `GET /system/diagnostics` | Deep model-by-model status (SCRFD, ArcFace, MiniFASNetV2, PaddleOCR, Haar fallback). |
| `GET /system/benchmarks` | Average / P50 / P95 latency per pipeline stage. |
| `GET /health` | Root-level liveness probe (outside the `/api/v1` prefix). |

Full request/response schemas, field-by-field, are documented in **[docs/API.md](docs/API.md)**.

---

## 12. Configuration Reference

All backend configuration is centralized in `backend/app/core/config.py` (Pydantic `Settings`, overridable via environment variables or a `.env` file in `backend/`). Key groups:

| Group | Notable settings | Defaults |
|---|---|---|
| Service identity | `APP_VERSION`, `API_V1_PREFIX`, `ENVIRONMENT` | `1.0.0-phase12`, `/api/v1`, `demonstration` |
| Blockchain | `BLOCKCHAIN_ENABLED`, `BLOCKCHAIN_LEDGER_TYPE`, `BLOCKCHAIN_CHAIN_STORAGE_PATH` | `True`, `development`, `app/data/blockchain_ledger.json` |
| Case limits | `MAX_DOCUMENTS_PER_CASE`, `CASE_SESSION_TTL_SECONDS` | `10`, `3600` |
| CORS | `CORS_ORIGINS`, `CORS_ORIGIN_REGEX` | localhost/127.0.0.1 on any port (Vite may hop ports) |
| Ingestion | `MAX_FILE_SIZE_MB`, `ALLOWED_MIME_TYPES`, `ALLOWED_EXTENSIONS` | `10`, `{jpeg,png,webp}` |
| OCR | `OCR_LANG`, `OCR_USE_ANGLE_CLS`, `OCR_USE_GPU` | `en`, `True`, `False` |
| Biometrics (M4) | `FACE_MATCH_THRESHOLD`, `FACE_DETECTION_CONFIDENCE_THRESHOLD`, `ANTI_SPOOF_THRESHOLD` | `0.30`, `0.50`, `0.70` |
| Model paths | `SCRFD_MODEL_PATH`, `ARCFACE_MODEL_PATH`, `MINIFASNET_MODEL_PATH` | under `app/models_weights/` |
| Registry (M5) | `REGISTRY_PROVIDER_MODE` and per-document overrides | `mock` (never calls a real government API by default) |
| Registry resilience | `REGISTRY_CONNECT_TIMEOUT`, `REGISTRY_READ_TIMEOUT`, `REGISTRY_TOTAL_TIMEOUT`, `REGISTRY_MAX_RETRIES` | `5s` / `10s` / `15s` / `1` |
| Risk (M6) | `RISK_THRESHOLD_MEDIUM/HIGH/CRITICAL`, `RISK_CONFIG_VERSION` | `25` / `50` / `75` |

Frontend configuration lives in `src/config/appConfig.js`:
- `APP_NAME` / `APP_SHORT_NAME` — change branding in exactly one place.
- `API_BASE_URL` — reads `VITE_API_BASE_URL` from `.env.local`, falls back to `http://localhost:9000`.
- `FEATURES` — `BACKEND_ENABLED`, `SAMPLE_DOCUMENTS`, `FORENSIC_PANEL`, `BLOCKCHAIN_AUDIT` toggles.

---

## 13. Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+ (LTS)
- 8 GB RAM minimum (16 GB recommended for concurrent OCR + face inference); ~5 GB free disk for model weights.
- Model weight files present in `backend/app/models_weights/`: `det_10g.onnx` (~16MB), `w600k_r50.onnx` (~170MB), `2.7_80x80_MiniFASNetV2.pth` (~1.2MB).

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS

pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload
```

On startup the app seeds the encrypted registry sandbox DB, initializes and warms up the PaddleOCR engine, and (via the diagnostics endpoint) reports the readiness of every ML model.

### Frontend

```bash
npm install
npm run lint     # oxlint — expect 0 errors, 0 warnings
npm run dev      # Vite dev server → http://localhost:4000 (proxies /api to :9000)
```

### Verify the stack is healthy

```bash
curl -s http://localhost:9000/health
curl -s http://localhost:9000/api/v1/system/health
curl -s http://localhost:9000/api/v1/system/diagnostics
```

Full step-by-step hardware/OS requirements and troubleshooting live in **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.

---

## 14. Testing

```bash
cd backend
python -m pytest tests/ -v
```

The suite (1060+ tests at last run) covers: per-document OCR/parser/validator/profile/registry logic for all seven document types, cross-document relationship and conflict-detection logic, every forensic sub-module (ELA, compression, photo boundary, metadata, stamp), the full biometric pipeline (detector, embedder, anti-spoof, matcher, quality gates), the risk engine and its rules/normalizers, the blockchain audit ledger, the case API, and the five end-to-end SIH demonstration scenarios (`test_sih_demo_scenarios.py`).

Frontend: `npm run lint` (oxlint) is the current automated check; there is no frontend unit-test runner configured yet.

---

## 15. Security & Privacy Posture

- **Zero PII/biometrics on-chain** — enforced at the schema-validation layer (see §7).
- **Upload hardening** — magic-byte verification (never trusts client `Content-Type`), a 10MB size ceiling, and Pillow's `Image.MAX_IMAGE_PIXELS` capped at 50M pixels to block decompression-bomb attacks.
- **Encrypted registry sandbox** — the mock government-registry database is stored encrypted at rest (`services/registry/db/crypto.py`).
- **Model integrity** — missing/corrupted model weight files raise explicit startup exceptions rather than silently degrading to fake predictions.
- **Cryptographic tamper evidence** — see the hash-chain design in §7.
- Full detail: **[docs/SECURITY.md](docs/SECURITY.md)**.

---

## 16. Known Limitations

- All registry lookups hit an **in-memory/local mock sandbox** — there is no real connection to any government database (UIDAI, Parivahan, immigration systems, etc.).
- The blockchain ledger is a **local permissioned hash-chain**, not a public/decentralized network.
- 2D presentation-attack detection (MiniFASNetV2) is not a substitute for 3D depth/IR liveness hardware.
- OCR/forensic accuracy degrades under extreme glare, low light (<50 lux), or >35° perspective skew.
- The frontend authentication/MFA layer (§10) is a client-only demo, not production-grade identity management.
- The system is architecturally barred from making autonomous admit/deny determinations — this is a design invariant, not a missing feature.

Full detail, including the ethical-AI anti-profiling invariant enforced in the risk engine: **[docs/LIMITATIONS.md](docs/LIMITATIONS.md)**.

---

## 17. Full Documentation Index

| Document | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Deep architectural walkthrough, evidence model, orchestrator detail |
| [docs/API.md](docs/API.md) | Full endpoint reference with request/response JSON schemas |
| [docs/SECURITY.md](docs/SECURITY.md) | Data-handling policy, ingestion hardening, cryptographic design |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Hardware/software prerequisites, setup, health-check verification |
| [docs/DEMO.md](docs/DEMO.md) | Five walkthrough scenarios (A–E) for evaluators/jury |
| [docs/LIMITATIONS.md](docs/LIMITATIONS.md) | Boundaries, edge cases, ethical-AI/anti-profiling policy |
| [docs/phase7-document-adapters.md](docs/phase7-document-adapters.md) | Document adapter architecture (build history) |
| [docs/phase8-multi-document.md](docs/phase8-multi-document.md) | Multi-document case engine (build history) |
| [docs/phase9-driving-license.md](docs/phase9-driving-license.md) | Driving license profile (build history) |
| [docs/phase10-national-id.md](docs/phase10-national-id.md) | National ID profile (build history) |
| [docs/phase11-border-permit.md](docs/phase11-border-permit.md) | Border permit profile (build history) |
| [docs/visa-reference-profile.md](docs/visa-reference-profile.md) | Visa profile reference notes |
| [PHASE_4_AUDIT_REPORT.md](PHASE_4_AUDIT_REPORT.md), [PHASE_4_COMPLETION.md](PHASE_4_COMPLETION.md), [PHASE_5_REGISTRY.md](PHASE_5_REGISTRY.md) | Historical phase build/completion logs at the repo root |

> Some `docs/*.md` files were written during earlier build phases and may reference older port numbers (`:5173`/`:8000`) or a lower test count — this root README reflects the current, verified state of the repository (frontend `:4000`, backend `:9000`, 1060+ passing tests) and should be treated as the source of truth where the two disagree.
