# Driving License Verification Architecture & Indian Reference Profile

**System:** AI-Based Fake Identity & Document Screening System  
**Version:** `0.9.0-phase9`  
**Document Type:** `driving_license`  
**Jurisdiction:** `IN` (India — Ministry of Road Transport and Highways / Sarathi Reference Profile)  
**Status:** Operational / Available  

---

> [!IMPORTANT]
> **Reference Profile Scope Disclaimer**  
> The Driving License implementation is an initial Indian reference profile and does not claim universal support for all Driving License layouts, historical formats, or international issuing authorities. Unsupported layouts return `UNSUPPORTED_PROFILE` or `INCONCLUSIVE` without guessing or synthetic field fabrication.

---

## 1. Architectural Philosophy & Zero-Rebuild Principle

Phase 9 integrates Driving License as the **third fully operational document type** alongside Passport and Visa. 

In strict adherence to the system architectural rules:
- **M1–M6 Analytical Engines Were NOT Rebuilt:** There is NO `dl_ocr_engine`, NO `dl_forensic_engine`, NO `dl_face_engine`, NO `dl_registry_engine`, and NO `dl_risk_engine`.
- **Pipeline Agnosticism:** Driving License documents pass through the generic verification pipeline:
  ```
  Uploaded Driving License Image
              ↓
  Generic Ingestion & Preprocessing
              ↓
  Common PaddleOCR Engine
              ↓
  Driving License Parser & Field Normalizer
              ↓
  Driving License Structural Validator (M2)
              ↓
  Common Forensics Engine (M3)
              ↓
  Common Biometrics / PAD Pipeline (M4)
              ↓
  Generic Registry Engine (M5) via DrivingLicenseRegistryAdapter
              ↓
  Generic Risk Engine (M6) with Normalized Evidence
              ↓
  Case & Cross-Document Intelligence (M8)
  ```

---

## 2. Indian Driving Licence Reference Profile

The reference profile is declaratively registered with `DocumentProfileRegistry` under key `driving_license`.

```json
{
  "document_type": "driving_license",
  "jurisdiction": "IN",
  "profile_version": "0.9.0",
  "display_name": "Driving License",
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
  "field_schema": [
    "name",
    "docNumber",
    "dob",
    "issuedDate",
    "expiry",
    "bloodGroup",
    "vehicleClasses",
    "issuingAuthority",
    "address",
    "state"
  ],
  "required_fields": [
    "name",
    "docNumber",
    "dob"
  ]
}
```

---

## 3. Supported Fields & Normalization

| Field Identifier | Common Label on Indian DL | Required? | Normalization Logic |
| :--- | :--- | :--- | :--- |
| `license_number` / `docNumber` | "DL No", "Licence No", "License No" | **Yes** | Strips visual separators (hyphens, spaces, slashes). Uppercased. Format checked against canonical MoRTH `^[A-Z]{2}\d{2}(?:19\|20)\d{2}\d{7}$`. |
| `name` | "Name", "Holder Name" | **Yes** | Uppercased, normalized whitespace, tokens cleaned. |
| `date_of_birth` / `dob` | "DOB", "Date of Birth" | **Yes** | Parsed to ISO `YYYY-MM-DD`. Supports `DD/MM/YYYY`, `DD-MM-YYYY`, `DD.MM.YYYY`. |
| `issued_date` / `valid_from` | "Issued", "Issue Date", "Valid From" | No | Parsed to ISO `YYYY-MM-DD`. |
| `expiry_date` / `valid_to` | "Valid Till", "Valid Upto", "NT Exp" | No | Parsed to ISO `YYYY-MM-DD`. |
| `blood_group` | "Blood Group", "BG" | No | Normalized to standard group notation: `A+`, `A-`, `B+`, `B-`, `AB+`, `AB-`, `O+`, `O-`. |
| `vehicle_classes` | "COV", "Class of Vehicles" | No | Normalized tokens (e.g. `MCWG`, `LMV`, `HMV`, `TRANS`). |
| `issuing_authority` | "Authority", "RTO", "Licensing Authority" | No | Normalized uppercase authority string. |
| `state` | State name / 2-letter prefix code | No | Derived from first 2 characters of license number (e.g., `DL` → `Delhi`, `MH` → `Maharashtra`, `TN` → `Tamil Nadu`). |
| `address` | "Address" | No | Preserved for officer inspection. Never ingested into generalized risk formulas. |

---

## 4. Module Integrations

### M1 — OCR & Deterministic Parsing
- Reuses common `ocr_engine` (PaddleOCR).
- Raw OCR regions, confidence scores, and bounding boxes are preserved without fabrication.
- Deterministic regex & spatial label-value pairing (`dl_parser.py`).
- If fewer than 2 regions are extracted or profile markers ("DRIVING LICENCE", "UNION OF INDIA", "DL NO") are absent, returns `UNSUPPORTED_PROFILE` or `INCONCLUSIVE`.

### M2 — Document Structural Validation (`dl_validator.py`)
- **Required Fields:** Ensures `docNumber`, `name`, and `dob` are extracted.
- **Identifier Format:** MoRTH standard format validation. Irregular formats yield `FORMAT_WARNING` (`severity: warning`), never `FORGED_DOCUMENT`.
- **Chronology & Expiry:** Enforces `issued_date <= expiry_date`, `valid_from <= valid_to`, and flags expired documents against reference date.
- **Age Eligibility:** Verifies bearer was at least 18 years old on license issue date.

### M3 — Tampering & Forensics
- Reuses common forensic pipeline (ELA, image quality, compression analysis, photo boundary analysis).
- Profile provides target regions (`card_boundary`, `portrait_area`).
- If card boundaries cannot be detected with confidence, status is returned as `UNAVAILABLE` or `INCONCLUSIVE` without fabricating coordinates.

### M4 — Biometrics & Face Processing
- Reuses SCRFD detector, Haar fallback, ArcFace embedding extractor (w600k_r50), and MiniFASNetV2 deep PAD classifier.
- If a portrait is detected on the DL card, standard single-face biometric matching against live capture is executed.
- If no face is detected or image quality is insufficient, returns `NOT_APPLICABLE` or `UNAVAILABLE`. Multi-face detections trigger standard M4 warnings.

### M5 — Registry Verification (`DrivingLicenseRegistryAdapter`)
- Development mock provider: `mock_driving_license_registry`.
- Source type: `DEVELOPMENT_MOCK` (visibly identified to officer and UI; never claimed as "Government Database").
- Deterministic mock records:
  - `TESTDL001` → `ACTIVE` (`MATCHED`)
  - `TESTDLEXPIRED001` → `EXPIRED`
  - `TESTDLREVOKED001` → `REVOKED`
  - `TESTDLSUSPENDED001` → `SUSPENDED`
  - `TESTDLMISMATCH001` → `MISMATCH`
  - `TESTDLTIMEOUT001` → `RegistryTimeout`
  - `TESTDLUNAVAIL001` → `RegistryProviderUnavailable`
  - Unknown numbers → `NOT_FOUND`

### M6 — Risk Engine Integration
- M6 remains completely document-agnostic. No `if document_type == "driving_license"` branches exist in the risk scoring logic.
- DL validation anomalies, registry statuses, and cross-document inconsistencies map to canonical `RiskEvidenceItem` structures.
- Double-counting protection groups related signals (e.g. M2 DL expiry + M5 registry expiry) under `CorrelationGroup.DOCUMENT_STATUS`.

---

## 5. Case & Cross-Document Intelligence (M8)

### Passport ↔ Driving License Relationship Profile
Registered in `DocumentRelationshipRegistry` with symmetric order-independence:
1. **Name Consistency (`RelationshipType.PERSON_NAME_CONSISTENCY`):**
   - Mode: `NORMALIZED_TOKEN_SET`
   - Exact token match → `MATCHED`
   - Subset overlap → `PARTIAL_MATCH` (low severity, never false fraud)
   - Disjoint tokens → `MISMATCH` (high severity)
2. **Date of Birth Consistency (`RelationshipType.PERSON_ATTRIBUTE_CONSISTENCY`):**
   - Mode: `NORMALIZED_DATE`
   - Mismatch → `MISMATCH` (high severity, mapped to `CorrelationGroup.DOB_CONSISTENCY`)

> [!NOTE]
> **Identifier Separation Invariant**  
> Driving License numbers and Passport numbers are distinct identification schemes. They are **never** compared across documents.

### Case Workflows
- Supports heterogeneous document cases: Passport-only, Visa-only, DL-only, Passport + Visa, Passport + DL, and 3-document cases (Passport + Visa + DL).
- Duplicate prevention: attempting to add a second DL to a case raises `DuplicateDocumentTypeError`.
- Replacement: adding with `replace=True` marks prior DL as `SUPERSEDED`, advances revision to 2, and purges superseded relationships.

---

## 6. Security, Privacy & Bias Protections

1. **Untrusted Input Handling:** OCR outputs and client payloads are treated as untrusted. Bounding box coordinates, text strings, and dates are sanitized before downstream evaluation.
2. **Immunity to Client Evidence Injection:** The server constructs registry requests and cross-document evidence server-side. Client-supplied risk or validation fields are ignored.
3. **Zero Demographic Profiling:**
   - State of issue, address, vehicle classes, and blood group are displayed for officer verification and consistency checks only.
   - **None** of these fields are ingested into generalized risk scoring formulas.
4. **Privacy:** Biometric embeddings and raw facial crops are ephemeral; raw OCR texts and addresses are never exposed in risk audit records.

---

## 7. Limitations & Future Extensions

- **Current Limitation:** Targets Indian smart card / MoRTH reference format. Paper booklets, laminated book licenses, or non-MoRTH state legacy formats may trigger `UNSUPPORTED_PROFILE`.
- **QR / Barcode:** Marked as `NOT_IMPLEMENTED` in Phase 9. Decodable QR payloads will be incorporated in future phases when cryptographic signature verification keys for state RTO authorities are available.
- **Future Extensibility Proof:** Tested in `test_national_id_extensibility.py`, demonstrating that a 4th document type (National ID) can be added solely via `DocumentProfile`, document adapter, and relationship profile without modifying core M1–M6 or case engines.
