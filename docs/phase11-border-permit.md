# Border Permit Verification Architecture & Reference Profile

**System:** AI-Based Fake Identity & Document Screening System  
**Version:** `0.11.0-phase11`  
**Document Type:** `border_permit`  
**Jurisdiction:** Regional Cross-Border Control Reference Profile  
**Status:** Operational / Available (Fifth Document Type)  

---

> [!IMPORTANT]
> **Reference Profile Scope Disclaimer**  
> This implementation is a **controlled Border Permit reference profile for prototype purposes and does not claim universal support for all Border Permit formats or issuing authorities.** Border permits vary substantially across jurisdictions, treaty zones, bilateral crossing agreements, and transport corridors. Unsupported layouts return `UNSUPPORTED_PROFILE` or `INCONCLUSIVE` without guessing, synthetic character fabrication, or heuristic hallucination.
>
> **Notice on Verification Claims:**
> - NO claim of universal Border Permit verification.
> - NO claim of official government registry access or legal certification.
> - NO claim of guaranteed authenticity or 100% fraud detection.
> - NO autonomous border entry/admissibility decision (final determination remains strictly with authorized border control officers).
> - NO demographic profiling or nationality-based adverse risk scoring.
> - Registry environment operates strictly as `DEVELOPMENT_MOCK`.

---

## 1. Architectural Philosophy & Zero-Rebuild Principle

Phase 11 implements **Border Permit** as the **fifth and final operational document type** in the current prototype scope, joining Passport, Visa, Driving License, and National ID.

In strict adherence to the system architectural rules:
- **Zero Engine Clones:** There is NO `border_permit_ocr_engine.py`, NO `border_permit_forensic_engine.py`, NO `border_permit_risk.py`, and NO `border_permit_face_engine.py`.
- **Generic Pipeline Agnosticism:** Border Permit documents pass through the existing generic verification architecture:
  ```
  Uploaded Border Permit Image
              ↓
  Generic Ingestion & Preprocessing
              ↓
  Common PaddleOCR Engine (M1)
              ↓
  Border Permit Parser & Normalizer
              ↓
  Border Permit Structural Validator (M2)
              ↓
  Common Forensic Engine (M3)
              ↓
  Common Biometric / PAD Pipeline (M4) [if portrait present]
              ↓
  Generic Registry Engine (M5) via BorderPermitRegistryAdapter
              ↓
  Generic Risk Engine (M6) with Correlation Protection
              ↓
  Multi-Document & Cross-Document Intelligence (M8)
              ↓
  Authorized Border Officer Review Workspace
  ```

---

## 2. Border Permit Reference Profile

The reference profile is declaratively registered in `DocumentProfileRegistry` under key `border_permit` (with aliases `borderpermit`, `borderPermit`):

```json
{
  "document_type": "border_permit",
  "display_name": "Border Permit",
  "jurisdiction": "REGIONAL_CORRIDOR",
  "profile_version": "0.11.0",
  "status": "AVAILABLE",
  "modules": {
    "ocr": "SUPPORTED",
    "validation": "SUPPORTED",
    "forensics": "SUPPORTED",
    "biometrics": "SUPPORTED",
    "registry": "SUPPORTED",
    "risk": "SUPPORTED"
  },
  "mrz_applicable": false,
  "portrait_applicable": true,
  "qr_applicable": true,
  "field_schema": [
    "name",
    "docNumber",
    "permit_number",
    "passport_number",
    "dateOfBirth",
    "nationality",
    "permitType",
    "validFrom",
    "validTo",
    "portOfEntry",
    "borderZone",
    "issuing_authority"
  ],
  "required_fields": ["name", "docNumber", "validFrom", "validTo"],
  "security_features": ["QR_CODE", "PORTRAIT_PHOTO", "GUILLOCHE_BACKGROUND", "OFFICIAL_STAMP"]
}
```

---

## 3. Supported Fields

The reference profile defines explicit fields extracted deterministically from visual inspection and machine zones:

| Field Name | Normalized Key | Cardinality | Example | Format / Validation Rule |
|:---|:---|:---|:---|:---|
| **Permit Number** | `permit_number`, `docNumber` | Required | `BP2026000123` | `BP-YYYY-NNNNNN` or `BPYYYYNNNNNN` |
| **Holder Name** | `name` | Required | `ALEX DUPONT` | Alphabetic token set, punctuation stripped |
| **Date of Birth** | `dateOfBirth`, `dob` | Optional | `1990-08-12` | ISO 8601 `YYYY-MM-DD` |
| **Passport Number** | `passport_number` | Optional | `P1234567` | Alphanumeric (6–10 chars), binds to passport |
| **Valid From** | `validFrom`, `valid_from` | Required | `2026-01-01` | ISO 8601 `YYYY-MM-DD` |
| **Valid To** | `validTo`, `expiry` | Required | `2026-12-31` | ISO 8601 `YYYY-MM-DD` |
| **Permit Type** | `permitType` | Optional | `ENTRY` | `ENTRY`, `TRANSIT`, `RESIDENT_BORDER`, `CREW`, `TEMPORARY` |
| **Port / Border Zone** | `portOfEntry`, `borderZone`| Optional | `NORTH GATE TERMINAL` | Alphanumeric corridor/gate descriptor |
| **Issuing Authority**| `issuing_authority` | Optional | `Border Management Authority` | Official issuing border service |
| **Nationality** | `nationality` | Optional | `FRA` | ISO 3-letter country code if explicitly stated |
| **QR Payload** | `qr_payload` | Optional | Delimited / JSON / XML | High-density 2D barcode identity binding |

---

## 4. M1 — Common OCR Pipeline

Border Permit reuses the existing `PaddleOCR` infrastructure with zero modifications:
1. **Ingestion:** Validates MIME type, dimensions (minimum $300 \times 300$, maximum $4096 \times 4096$), aspect ratio, and color space.
2. **Preprocessing:** Performs illumination normalization, optional skew angle detection and correction, and edge contrast optimization.
3. **Inference:** Extracts raw text spans, confidence scores ($0.0–1.0$), and 4-point bounding boxes.
4. **Deterministic Parser (`border_permit_parser.py`):**
   - Resolves spatial bounding boxes to link field labels (e.g. `PERMIT NO:`) with value tokens.
   - Detects layout anomalies: rejects non-permit layouts returning `is_supported_layout=False`.
   - Flags OCR ambiguity (`AMBIGUOUS_IDENTIFIER`) when characters could represent multiple conflicting numbers.
   - Preserves raw values alongside normalized tokens with field confidence and bounding boxes.

---

## 5. M2 — Border Permit Structural Validation

Validation (`border_permit_validator.py`) applies deterministic structural and temporal rules:
1. **Required Fields Check:** Verifies presence of `name`, `docNumber` / `permit_number`, `valid_from`, and `valid_to`. Missing fields produce `CRITICAL` issues (`MISSING_REQUIRED_FIELD`).
2. **Permit Number Syntax:** Enforces canonical pattern `^BP-?\d{4}-?\d{6}$`. Malformed numbers produce `INVALID_PERMIT_NUMBER_FORMAT`.
3. **Date Chronology:** Validates that dates are syntactically valid calendar dates. Inversions where `valid_from > valid_to` generate `INVALID_DATE_RANGE`.
4. **Temporal Status Classification:**
   - Evaluated against verification timestamp.
   - `ACTIVE`: Current date is within `[valid_from, valid_to]`.
   - `EXPIRED`: Current date exceeds `valid_to`. Classified as `warning` (`DOCUMENT_EXPIRED`), **never** confused with forgery.
   - `NOT_YET_VALID`: Current date precedes `valid_from`. Classified as `warning` (`DOCUMENT_NOT_YET_VALID`).
5. **Passport Binding Syntax:** If `passport_number` is present on the permit, validates that it matches standard passport numbering conventions.
6. **QR/OCR Consistency:** Cross-validates OCR-extracted permit number and traveler name against decoded QR payload fields.

---

## 6. Identifier Handling & Normalization

- **Permit Number Normalization:**
  - Standard format: `BP-YYYY-NNNNNN` $\to$ `BPYYYYNNNNNN`.
  - Hyphens and spaces are stripped only according to profile normalization rules.
  - Case is converted to upper case.
- **Ambiguity Detection:**
  - Scans for common OCR optical substitution risks (`O` vs `0`, `I` vs `1`, `B` vs `8`, `S` vs `5`) in numeric zones.
  - If characters fail structural parity, marks field as `AMBIGUOUS_IDENTIFIER` and flags for officer manual inspection.
  - Never silently mutates ambiguous characters.

---

## 7. QR / Barcode Verification & Payload Security

High-density 2D barcodes or QR codes on border permits contain traveler tokens for expedited border gate crossing:
1. **Detection & Decoding:** Located via OpenCV/pyzbar scanning within the document image.
2. **Untrusted Input Quarantine:**
   - Decoded payloads are treated as **untrusted external input**.
   - Payloads are never executed, evaluated as code, or used to redirect network requests.
   - Payloads cannot overwrite server-side risk scores, validation outcomes, or registry responses.
3. **Consistency Verification:**
   - Extracted QR permit number $\leftrightarrow$ OCR permit number.
   - Extracted QR traveler name $\leftrightarrow$ OCR traveler name.
   - Mismatch triggers `BORDER_PERMIT_QR_OCR_MISMATCH` ($status=\text{MISMATCH}$).
4. **Authentication Level Semantics:**
   - Successful decoding is explicitly labeled:
     ```
     Detection: FOUND
     Payload: DECODED
     Cryptographic Authentication: NOT VERIFIED
     ```
   - In the absence of a signed digital certificate verified against a trusted root CA, the platform **never** declares "QR Authenticated".

---

## 8. M3 — Forensic Analysis Integration

Reuses the platform's unified Module 3 Forensic Engine without creating document-specific forensic engines:
- **Profile-Driven Forensic Regions:**
  - `photo`: Bounding box around traveler portrait.
  - `permit_number`: Primary identifier area.
  - `text_zone`: Demographic and validity text block.
  - `qr_code`: 2D barcode module area.
- **Techniques Executed:**
  - Error Level Analysis (ELA) for digital resaving and compression artifacts.
  - Edge and gradient continuity across photo and text boundaries.
  - Copy-move cloning and local anomaly detection.
  - Image quality assessment (sharpness, blur, underexposure, overexposure).
- **Coordinate Integrity:** If a region is absent (e.g. permit without portrait), it returns `UNAVAILABLE` or `NOT_APPLICABLE`. Coordinates are never fabricated.

---

## 9. M4 — Biometrics Integration & Safety

Reuses the unified Module 4 Face Biometrics & Presentation Attack Detection (PAD) pipeline:
- **Applicability:** Executed only when a traveler portrait photo is detected on the permit and a live face capture or reference passport portrait is provided.
- **Pipeline:** SCRFD face detection $\to$ 5-point facial landmark alignment $\to$ ArcFace deep feature embedding ($512$-d vector) $\to$ MiniFASNetV2 deep PAD analysis.
- **Biometric Safety Quarantine:**
  - Raw face crops and 512-d feature vectors are strictly quarantined within Module 4.
  - Raw embeddings are **never** passed to Module 6 Risk Engine, logged, or sent to client browsers.
  - Module 6 receives only normalized telemetry: `FACE_MATCH` / `FACE_MISMATCH`, match confidence ($0.0–1.0$), and PAD verdict (`PASS`, `FAIL`, `UNCERTAIN`).
- **Absence Handling:** If no portrait is present on the document, status returns `NOT_APPLICABLE` with zero adverse risk penalty.

---

## 10. M5 — Registry Verification

Implements `BorderPermitRegistryAdapter` and `MockBorderPermitRegistryProvider`:
- **Architecture:** Communicates via generic `RegistryEngine` through normalized `RegistryVerificationRequest` and `RegistryVerificationResponse`.
- **Source Disclosure:** Visibly stamped with `source_type: "development_mock"`. The UI displays `DEVELOPMENT MOCK — not real government database`.
- **Deterministic Test Records:**
  - `TESTBP001` / `BP2026000123`: Active valid permit ($\to \text{MATCHED}$).
  - `TESTBPEXPIRED001`: Expired permit record ($\to \text{EXPIRED}$).
  - `TESTBPREVOKED001`: Revoked permit record ($\to \text{REVOKED}$).
  - `TESTBPSUSPENDED001`: Suspended permit record ($\to \text{SUSPENDED}$).
  - `TESTBPMISMATCH001`: Registered under different name ($\to \text{MISMATCH}$).
  - `TESTBPTIMEOUT001`: Simulates provider timeout ($\to \text{TIMEOUT}$).
  - `TESTBPUNAVAIL001`: Simulates provider outage ($\to \text{UNAVAILABLE}$).
  - Any unknown permit number: $\to \text{NOT_FOUND}$.
- **Failure Non-Penalization:** Network timeouts and provider outages are classified as `REGISTRY_UNAVAILABLE` or `TIMEOUT`, **never** flagged as fraud.

---

## 11. M8 — Cross-Document Intelligence

Border Permit integrates into the platform's multi-document graph via registered `RelationshipProfile` definitions:

### 11.1 Primary Relationship: Border Permit $\leftrightarrow$ Passport
- **Identifier Binding (Critical):** `Border Permit.passport_number` $\leftrightarrow$ `Passport.document_number` (`ComparisonMode.STRICT`). Mismatch triggers high-severity risk signal `border_permit_passport_number_mismatch`.
- **Person Name Consistency:** `Border Permit.name` $\leftrightarrow$ `Passport.name` (`ComparisonMode.NORMALIZED_TOKEN_SET`).
- **Date of Birth Consistency:** `Border Permit.date_of_birth` $\leftrightarrow$ `Passport.date_of_birth` (`ComparisonMode.EXACT_DATE`).

### 11.2 Secondary Relationships
- **Border Permit $\leftrightarrow$ National ID:** Name consistency and Date of Birth / Year of Birth consistency where both documents are present in the case.
- **Order Independence:** Upload order (`Border Permit \to Passport` vs `Passport \to Border Permit`) produces identical relationship graphs and risk evidence.

---

## 12. M6 — Risk Engine Integration & Anti-Double-Counting

Border Permit evidence maps to platform-standard `RiskEvidenceItem` objects evaluated by the document-agnostic `RiskAggregator`:
- **Correlation Grouping:** Discrepancies between Border Permit and Passport belong to `CorrelationGroup.BORDER_PERMIT_PASSPORT_BINDING`.
- **Exponential Decay Factor ($0.50 \times$):** When both M2 structural validation and M8 cross-document engine identify the same underlying passport mismatch, the secondary signal is discounted by $50\%$ to prevent artificial score inflation.
- **Zero Demographic Profiling Immunity:** Nationality, border gate/zone, permit category, and travel purpose are strictly barred from generating adverse risk score contributions.

---

## 13. Privacy & Data Minimization

- **Identifier Masking:** Sensitive identifiers (e.g. linked passport numbers, national ID numbers) are masked in audit trails and system logs (e.g., `P123****`).
- **Evidence Referencing:** Module 6 risk evidence stores field references and discrepancy summaries rather than replicating full traveler identity blocks.
- **Biometric Isolation:** Raw biometric embeddings are cleared from memory immediately upon completion of pairwise cosine comparison.

---

## 14. Security & Tamper Resistance

- **Server-Authoritative Validation:** The API rejects or ignores any client-supplied risk scores, registry outcomes, cross-document statuses, or QR authentication states.
- **Input Sanitization:** OCR text and QR payload strings are sanitized to prevent XSS or injection vulnerabilities when rendered in officer workstations.
- **Session Isolation:** Server-side sessions and document intake IDs are tied to verified case tokens, preventing cross-tenant or cross-session leakage.

---

## 15. Supported Profile Limitations

1. **Prototype Reference Layout:** Designed for standard rectangular single-sheet or card border permits with prominent permit numbers, traveler demographics, validity periods, and optional QR/port descriptors.
2. **Historical & Non-Standard Layouts:** Handwritten permits, non-Latin script permits, or legacy paper passes without clear key-value structure are unsupported and rejected safely as `UNSUPPORTED_PROFILE`.
3. **Cryptographic Validation:** Digital signatures embedded in QR codes require a trusted government Public Key Infrastructure (PKI) root store; absent such infrastructure, QR payloads remain `NOT VERIFIED`.

---

## 16. Future Extensions

1. **Multi-Jurisdiction Profiles:** Add specific regional profiles (e.g. EU Local Border Traffic Permit, US Border Crossing Card / BCC, Hong Kong-Macau Entry Permit) by defining declarative profiles in `DocumentProfileRegistry`.
2. **PKI Signature Verification:** Connect to ICAO PKD or national trust anchors to cryptographically verify digital seal signatures on 2D barcodes.
3. **Authorized Agency Adapters:** Replace `MockBorderPermitRegistryProvider` with secured REST/SOAP adapters connecting to authorized bilateral border authority databases via mTLS.
