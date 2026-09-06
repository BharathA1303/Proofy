# API Reference — AI-Based Fake Identity & Document Screening System

**Version:** `1.0.0-phase12`  
**Base URL:** `http://localhost:8000/api/v1`  
**OpenAPI Docs:** `http://localhost:8000/docs`  
**Format:** JSON / Multipart Form  

---

## 1. Verification & Case Orchestration

### `POST /verification/orchestrate`
Executes the full 11-stage automated screening pipeline for a single document.

**Request:** `multipart/form-data`
- `file`: Binary image file (JPEG, PNG, WEBP, max 10MB)
- `document_type`: `passport` | `visa` | `driving_license` | `national_id` | `border_permit`
- `case_id`: *(Optional)* Multi-document case identifier

**Response:** `200 OK`
```json
{
  "verification_id": "VER-9A8B7C6D5E4F",
  "correlation_id": "corr-11223344-5566",
  "document_id": "DOC-P01",
  "document_type": "passport",
  "current_stage": "OFFICER_REVIEW",
  "stages": [
    { "stage": "OCR_PROCESSING", "status": "completed", "duration_ms": 1180.5 },
    { "stage": "VALIDATING", "status": "completed", "duration_ms": 28.3 },
    { "stage": "FORENSICS", "status": "completed", "duration_ms": 720.1 },
    { "stage": "BIOMETRIC_PROCESSING", "status": "completed", "duration_ms": 310.4 },
    { "stage": "REGISTRY_VERIFICATION", "status": "completed", "duration_ms": 52.1 },
    { "stage": "RISK_ASSESSMENT", "status": "completed", "duration_ms": 14.2 },
    { "stage": "OFFICER_REVIEW", "status": "pending", "duration_ms": 0.0 }
  ],
  "evidence_items": [ ... ],
  "anchored_events": ["CASE_CREATED", "DOCUMENT_UPLOADED", "EVIDENCE_ANCHORED"],
  "total_duration_ms": 2305.6,
  "officer_review_pending": true,
  "blockchain_integrity": {
    "status": "ANCHORED",
    "block_index": 12,
    "chain_valid": true
  }
}
```

---

### `POST /verification/case`
Initialize a new multi-document verification case.

**Request:** `application/json`
```json
{
  "notes": "Standard border control multi-document case"
}
```

**Response:** `201 Created`
```json
{
  "case_id": "CASE-1A2B3C4D",
  "created_at": "2026-09-06T12:00:00Z",
  "status": "ACTIVE",
  "documents": [],
  "relationships": [],
  "risk_assessment": null,
  "blockchain_audit": {
    "events_count": 1,
    "chain_valid": true,
    "ledger_type": "development_sandbox",
    "latest_block_hash": "6a7b8c..."
  }
}
```

---

### `POST /verification/case/{case_id}/documents`
Upload and attach a document to an existing case.

**Request:** `multipart/form-data`
- `document_type`: `passport` | `visa` | `driving_license` | `national_id` | `border_permit`
- `file`: Document image file
- `replace`: `true` | `false` (default: `false` — prevents duplicate document types)

**Response:** `200 OK` (Updated `VerificationCaseResponse` with recalculated cross-document relationships)

---

### `DELETE /verification/case/{case_id}/documents/{document_id}`
Removes a document from an active case and triggers automatic risk and relationship invalidation.

**Response:** `200 OK`

---

## 2. Cryptographic Blockchain Audit & Integrity

### `GET /audit/{target_id}/chain`
Retrieves the cryptographic audit chain of blocks for a verification target or case.

**Parameters:**
- `target_id`: Case ID (`CASE-...`) or Verification ID (`VER-...`)

**Response:** `200 OK`
```json
{
  "target_id": "CASE-SIH-001",
  "ledger_name": "LOCAL DEVELOPMENT LEDGER",
  "source_type": "development_sandbox",
  "ledger_type": "development_sandbox",
  "chain_valid": true,
  "total_blocks": 3,
  "blocks": [
    {
      "block_index": 1,
      "previous_hash": "0000000000000000000000000000000000000000000000000000000000000000",
      "block_hash": "4a5b6c...",
      "timestamp": 1788700100.0,
      "target_id": "CASE-SIH-001",
      "event_type": "CASE_CREATED",
      "evidence_hash": "0000000000000000000000000000000000000000000000000000000000000000",
      "record_version": "1.0.0",
      "system_version": "1.0.0-phase12",
      "metadata": { "notes": "SIH Demo Case" }
    },
    {
      "block_index": 2,
      "previous_hash": "4a5b6c...",
      "block_hash": "9d8e7f...",
      "timestamp": 1788700105.0,
      "target_id": "CASE-SIH-001",
      "event_type": "EVIDENCE_ANCHORED",
      "evidence_hash": "382057c07e13...",
      "record_version": "1.0.0",
      "system_version": "1.0.0-phase12",
      "metadata": { "items_count": 4 }
    }
  ]
}
```

---

### `POST /audit/{target_id}/verify`
Cryptographically verifies that the live stored evidence has not been tampered with by recalculating its canonical SHA-256 digest and comparing against the anchored block.

**Response (Integrity Confirmed):** `200 OK`
```json
{
  "target_id": "CASE-SIH-001",
  "integrity_status": "VALID",
  "chain_valid": true,
  "events_verified": 3,
  "chain_length": 3,
  "calculated_evidence_hash": "382057c07e13...",
  "anchored_evidence_hash": "382057c07e13...",
  "details": "All 3 audit events and cryptographic chain verified successfully."
}
```

**Response (Tampering Detected):** `200 OK`
```json
{
  "target_id": "CASE-SIH-001",
  "integrity_status": "INTEGRITY_FAILURE",
  "chain_valid": true,
  "events_verified": 3,
  "chain_length": 3,
  "calculated_evidence_hash": "ea6ead85dc7a...",
  "anchored_evidence_hash": "382057c07e13...",
  "details": "Evidence hash mismatch: Current evidence has been modified or corrupted since ledger anchoring."
}
```

---

### `POST /audit/{target_id}/officer-decision`
Records an authoritative, authorized human officer determination onto the immutable ledger.

**Request:** `application/json`
```json
{
  "officer_id": "OFFICER-BORDER-42",
  "decision": "CLEAR_ADMIT",
  "reason": "All documents verified, face match confirmed, zero fraud signals",
  "notes": "Admitted on standard 30-day tourism visa"
}
```

*Permitted Decisions:*
- `CLEAR_ADMIT` (or `ADMIT`)
- `REFER_TO_SECONDARY`
- `REFUSE_ENTRY`
- `REQUEST_ADDITIONAL_DOCUMENTS` (or `REQUEST_ADDITIONAL_DOCS`)

**Response:** `201 Created`
```json
{
  "target_id": "CASE-SIH-001",
  "decision": "CLEAR_ADMIT",
  "officer_id": "OFFICER-BORDER-42",
  "reason": "All documents verified, face match confirmed, zero fraud signals",
  "notes": "Admitted on standard 30-day tourism visa",
  "timestamp": 1788700200.0,
  "block_index": 3,
  "block_hash": "5b07e430d5de...",
  "event_type": "OFFICER_REVIEWED",
  "status": "RECORDED",
  "payload": { ... }
}
```

---

## 3. System Diagnostics & Telemetry

### `GET /system/health`
High-level service operational health and subsystem readiness.

### `GET /system/diagnostics`
Detailed ML/CV model checks:
- SCRFD face detector ONNX model file check and runtime status
- ArcFace embedding generator ONNX model status
- MiniFASNet PAD anti-spoof model status
- PaddleOCR engine status
- Haar cascade fallback detector status

### `GET /system/benchmarks`
Empirical latency statistics:
- Average, P50, and P95 execution latencies across all screening stages
- Number of recorded runs in the current session
