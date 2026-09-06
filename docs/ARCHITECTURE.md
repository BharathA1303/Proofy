# System Architecture — AI-Based Fake Identity & Document Screening System

**Version:** `1.0.0-phase12`  
**Operational Status:** Evaluation & Demonstration Sandbox  
**Scope:** Generic, Document-Agnostic Border Screening Platform  

---

## 1. Executive Architectural Principle

The system is designed as an **AI-assisted decision-support platform** for authorized immigration, customs, and law-enforcement officers.  
**Critical Governance Rule:** The automated pipeline terminates at `COMPLETED`, meaning automated data processing and risk aggregation have finished. The system **never** outputs autonomous legal determinations such as `CLEARED`, `DENIED`, or `REFUSED`. The ultimate legal and administrative authority resides solely with the human officer.

```
       ┌──────────────────────────────┐
       │   Traveler Document Upload   │
       └──────────────┬───────────────┘
                      │
                      ▼
       ┌──────────────────────────────┐
       │ Generic Document Pipeline    │
       │   M1: Extraction (OCR)       │
       │   M2: Document Validation    │
       │   M3: Forensics & Tampering  │
       │   M4: Biometrics & PAD       │
       │   M5: Registry Comparison    │
       └──────────────┬───────────────┘
                      │
                      ▼
       ┌──────────────────────────────┐
       │ Cross-Document Intelligence  │
       │ (Phase 8 Multi-Doc Cases)    │
       └──────────────┬───────────────┘
                      │
                      ▼
       ┌──────────────────────────────┐
       │     M6 Risk Engine           │
       │ (Advisory Evaluation Only)   │
       └──────────────┬───────────────┘
                      │
                      ▼
       ┌──────────────────────────────┐
       │ Human Officer Review Station │
       │ (Authoritative Decision)     │
       └──────┬────────────────┬──────┘
              │                │
              ▼                ▼
     ┌─────────────────┐ ┌───────────────────────────┐
     │ Secure Database │ │ Blockchain Audit Ledger   │
     │ (Sensitive Data │ │ (Zero PII · Canonical     │
     │  Encrypted)     │ │  SHA-256 Hashes Only)     │
     └─────────────────┘ └───────────────────────────┘
```

---

## 2. Document Profile Architecture

Rather than creating siloed, hardcoded pipelines for each credential type, the platform utilizes a **Generic Document Profile Engine** (`DocumentProfileRegistry`). Every supported document maps to a declarative profile specification:

| Profile Key | Document Name | Layout / Extraction Standard | Primary Security Features | Reference Implementation |
|---|---|---|---|---|
| `passport` | International Passport | ICAO Doc 9303 TD3 (MRZ) | Optical checksums, ghost photo, UV ELA | Full reference profile |
| `visa` | Travel Visa | ICAO Doc 9303 MRVA/B & Text | Machine-readable lines, passport binding | Full reference profile |
| `driving_license` | Driving License | Regional DL standard (Field keys) | Microprint, photo boundary, DL registry | Controlled Indian DL profile |
| `national_id` | National Identity Card | Bilingual layout & 2D secure QR | Secure QR payload, token-set name match | Controlled Indian Aadhaar profile |
| `border_permit` | Cross-Border Entry Permit | Fixed multi-field border permit format | Permit serial, security stamp, validity | Controlled cross-border profile |

Each profile defines:
1. **Extraction Adapters**: Parser logic for OCR text, MRZ, or 2D barcodes.
2. **Validation Rules**: Checksum algorithms, date chronologies, expiry checks.
3. **Forensic Profiles**: Expected localized photo boundaries, ELA thresholds.
4. **Registry Providers**: Standardized lookup adapters to reference sandboxes.

---

## 3. Normalized Evidence Model

Every pipeline module (M1–M6), cross-document relation, and case action emits a standardized evidence unit conforming to `NormalizedEvidenceItem`:

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

Evidence packages (`EvidencePackage`) group all evidence for a verification session or case. The package provides a deterministic `to_canonical_dict()` method that sorts all keys and items lexicographically to enable cryptographic hashing.

---

## 4. Blockchain & Immutable Audit Architecture

### Off-Chain vs. On-Chain Separation
To guarantee strict compliance with data privacy regulations (GDPR, DPDP Act, and international biometric privacy standards):
- **Zero Sensitive Data On-Chain:** No traveler photos, face crops, 512-dimensional biometric embeddings, raw OCR transcripts, names, dates of birth, or addresses are ever written to the blockchain.
- **On-Chain Evidence Digests:** Only canonical SHA-256 hashes of the normalized evidence packages and event metadata are anchored.

### Blockchain Ledger Interface (`BlockchainLedger`)
The audit layer is abstracted through a clean interface:
- `append_block(target_id, event_type, evidence_hash, metadata)`: Appends an immutable block.
- `verify_chain()`: Cryptographically validates the hash chain from Genesis ($0^{64}$) to the chain head.
- `get_chain(target_id)`: Retrieves historical blocks for a given case or verification target.

### Hash-Chained Structure
Each block cryptographically seals the previous block's hash:
$$H_i = \text{SHA256}(i \parallel H_{i-1} \parallel t \parallel \text{target\_id} \parallel \text{event\_type} \parallel \text{evidence\_hash} \parallel \text{version} \parallel \text{metadata})$$

### Chain of Custody Milestones
1. `CASE_CREATED`
2. `DOCUMENT_UPLOADED`
3. `OCR_COMPLETED`
4. `VALIDATION_COMPLETED`
5. `FORENSICS_COMPLETED`
6. `BIOMETRIC_COMPLETED`
7. `REGISTRY_COMPLETED`
8. `CROSS_DOCUMENT_EVALUATED`
9. `RISK_ASSESSMENT_COMPLETED`
10. `OFFICER_REVIEWED` (Authoritative decision anchored)

---

## 5. End-to-End Verification Orchestrator

The verification orchestrator (`VerificationOrchestrator`) coordinates the verification lifecycle across 11 discrete stages:

```text
STANDBY
   ↓
DOCUMENT_SELECTED
   ↓
UPLOADING
   ↓
OCR_PROCESSING
   ↓
VALIDATING
   ↓
FORENSICS
   ↓
BIOMETRIC_PENDING
   ↓
BIOMETRIC_PROCESSING
   ↓
REGISTRY_VERIFICATION
   ↓
RISK_ASSESSMENT
   ↓
OFFICER_REVIEW
   ↓
COMPLETED
```

### Telemetry & Fault Tolerance
- **Correlation IDs:** Every verification request generates a UUID correlation ID traced across logs.
- **Stage Benchmarking:** Start/end timestamps record execution latencies for OCR, validation, forensics, biometrics, registry, risk engine, and blockchain anchoring.
- **Failure Resilience:** If the blockchain ledger or registry sandbox becomes temporarily unreachable, the core verification pipeline completes normally, queueing audit events as `PENDING` without dropping evidence.
