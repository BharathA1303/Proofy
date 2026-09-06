# National ID Verification Architecture & Indian Reference Profile

**System:** AI-Based Fake Identity & Document Screening System  
**Version:** `0.10.0-phase10`  
**Document Type:** `national_id`  
**Jurisdiction:** `IN` (India — Unique Identification Authority of India / Aadhaar Reference Profile)  
**Status:** Operational / Available  

---

> [!IMPORTANT]
> **Reference Profile Scope Disclaimer**  
> This implementation is an **Indian National ID reference profile** (modeled after standard UIDAI Aadhaar physical & digital card layouts) and does NOT claim universal support for all National ID formats, countries, historical card layouts, or foreign national identities. Unsupported layouts return `UNSUPPORTED_PROFILE` or `INCONCLUSIVE` without guessing, synthetic character fabrication, or heuristic hallucination.

---

## 1. Architectural Philosophy & Zero-Rebuild Principle

Phase 10 introduces National ID as the **fourth real operational document type** alongside Passport, Visa, and Driving License.

In strict adherence to the system architectural rules:
- **Zero Engine Clones:** There is NO `national_id_ocr_engine`, NO `national_id_forensic_engine`, NO `national_id_face_engine`, NO `national_id_registry_engine`, and NO `national_id_risk_engine`.
- **Generic Pipeline Agnosticism:** National ID documents pass through the generic verification pipeline:
  ```
  Uploaded National ID Card Image
              ↓
  Generic Ingestion & Preprocessing
              ↓
  Common PaddleOCR Engine
              ↓
  National ID Parser & Field Normalizer
              ↓
  National ID Structural Validator (M2) [Verhoeff D5 Checksum]
              ↓
  Common Forensics Engine (M3)
              ↓
  Common Biometrics / PAD Pipeline (M4)
              ↓
  Generic Registry Engine (M5) via NationalIdRegistryAdapter
              ↓
  Generic Risk Engine (M6) with Normalized Evidence
              ↓
  Case & Cross-Document Intelligence (M8)
  ```

---

## 2. Indian National ID Reference Profile

The reference profile is declaratively registered with `DocumentProfileRegistry` under key `national_id` (with aliases `nid`, `aadhaar`).

```json
{
  "document_type": "national_id",
  "jurisdiction": "IN",
  "profile_version": "0.10.0",
  "display_name": "National ID",
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
    "identity_number",
    "masked_identity_number",
    "date_of_birth",
    "year_of_birth",
    "gender",
    "address",
    "issuing_authority",
    "qr_payload",
    "qr_decoded"
  ],
  "required_fields": [
    "name",
    "identity_number"
  ]
}
```

---

## 3. Supported Fields & Normalization

| Field Identifier | Common Indian Reference Labels | Required? | Normalization Logic |
| :--- | :--- | :--- | :--- |
| `identity_number` / `identityNumber` | 12-digit numeric layout (`XXXX XXXX XXXX`) | **Yes** | Strips space/hyphen separators. Validates exact 12-digit length. Strictly numerical. |
| `masked_identity_number` | Masked representation | Auto | Normalized to `XXXX XXXX NNNN` (masking initial 8 digits, preserving last 4). |
| `name` | Bearer full name | **Yes** | Uppercased, normalized whitespace. Filters out government headings ("GOVERNMENT OF INDIA", "UNIQUE IDENTIFICATION AUTHORITY OF INDIA"). |
| `date_of_birth` / `dob` | "DOB:", "Date of Birth:" | Optional* | ISO `YYYY-MM-DD`. Supports `DD/MM/YYYY`, `DD-MM-YYYY`, `DD.MM.YYYY`. |
| `year_of_birth` / `yob` | "Year of Birth:", "YOB:" | Optional* | 4-digit integer (e.g. `1992`). Plausibility checked between 1900 and current year. |
| `gender` | "MALE", "FEMALE", "TRANSGENDER" | Optional | Canonical values: `M`, `F`, `T`. Used **strictly** for document consistency, never risk scoring. |
| `address` | "Address:", "S/O", "D/O", "W/O" | Optional | Multiline address string. Retained for document consistency only. |
| `issuing_authority` | "Government of India", "UIDAI" | No | Standardized authority descriptor. |
| `qr_payload` / `qr_decoded` | QR / Secure barcode data | Optional | Decoded XML, JSON, or delimited payload. |

*\*Note: Either `date_of_birth` or `year_of_birth` is required for temporal identification. Year-of-birth is explicitly distinct and never fabricated into an artificial full date.*

---

## 4. M1 — Common OCR & Dedicated Parser

- **Engine Reuse:** Raw OCR runs through the existing preprocessor and PaddleOCR engine, returning raw lines, bounding boxes, and recognition confidence scores.
- **Dedicated Extraction (`NationalIdParser`):**
  - Detects Indian National ID markers (`Government of India`, `UIDAI`, `Unique Identification Authority of India`, 12-digit grouped patterns).
  - Employs spatial and label-based extraction to separate bearer name from institutional headers.
  - Detects ambiguous identifiers: If OCR detects confusing characters in the identity slot (e.g. `1234 56B8 9012`), the system marks `is_ambiguous=True` and issues an `AMBIGUOUS_IDENTIFIER` issue instead of silently converting `B → 8`.
  - Rejects completely unsupported layouts with `UNSUPPORTED_PROFILE` or `INCONCLUSIVE`.

---

## 5. M2 — Structural Validation & Verhoeff Checksum

The `NationalIdValidator` evaluates:
1. **Required Fields:** Presence of bearer name and identity number.
2. **Identifier Syntax:** 12-digit numeric constraint (`^[2-9]\d{11}$` canonical format).
3. **Official Verhoeff D5 Algorithm:**
   - Evaluates the 12th check digit using the standard Dihedral Group $D_5$ multiplication and permutation matrices.
   - Outputs: `PASS`, `FAIL`, or `INCONCLUSIVE`.
   - **Crucial Rule:** A checksum failure produces `FORMAT_WARNING` with an explanation: `"National ID check digit validation failed (possible OCR misrecognition or transcription error)"`. It is **never** labeled as automatic proof of document forgery.
4. **DOB / YOB Plausibility:** Verifies birth dates are not in the future and fall within human lifetime limits (1900–present).

---

## 6. QR / Barcode Architecture & Semantics

- **Detection & Decoding:** Supports standard UIDAI QR formats (plain XML `<PrintLetterBarcodeData ...>`, JSON payloads, and delimited format strings).
- **Semantics:**
  - When a QR payload is read successfully, it is labeled:
    ```
    Payload: PAYLOAD_DECODED
    Authentication: NOT VERIFIED
    ```
  - It is **never** declared `AUTHENTICATED` unless full offline cryptographic public-key certificate verification against UIDAI root keys is executed.
- **Field Consistency:**
  - Compares QR extracted attributes (`uid`, `name`, `dob`, `yob`, `gender`) against visual OCR extracted attributes.
  - Matches produce `RelationshipStatus.MATCHED`.
  - Inconsistencies produce `RelationshipStatus.MISMATCH` with severity `HIGH`, triggering an evidence signal for officer review.

---

## 7. M3 Forensics & M4 Biometrics Integration

- **Forensic Engine (M3):**
  - Reuses the shared forensic pipeline without any document-type branching.
  - Evaluates image quality, error level analysis (ELA), photo boundary consistency, and copy-move/compression artifacts.
  - If photo region detection is uncertain, regions are marked `UNAVAILABLE` or `INCONCLUSIVE` — coordinates are never fabricated.
- **Biometric Pipeline (M4):**
  - Evaluates bearer portrait via SCRFD face detector, landmark alignment, ArcFace 512D deep embeddings, and MiniFASNetV2 Presentation Attack Detection (PAD).
  - If a portrait is not found on the card, biometrics evaluates to `NOT_APPLICABLE` or `UNAVAILABLE` rather than failing fraud checks.
  - Raw face embeddings and raw face crops are strictly quarantined and never embedded into M6 risk evidence.

---

## 8. M5 — Registry Verification & Mock Provider

- **Adapter Pattern:** `NationalIdRegistryAdapter` maps session OCR and validation data into standard `RegistryVerificationRequest`.
- **Mock Provider:** `MockNationalIdRegistryProvider` (`source_type: "development_mock"`):
  - Deterministic test records:
    - `987654321098` / `TESTNID001` → `MATCHED` (`ACTIVE`)
    - `TESTNIDEXPIRED001` → `EXPIRED`
    - `TESTNIDREVOKED001` → `REVOKED`
    - `TESTNIDSUSPENDED001` → `SUSPENDED`
    - `TESTNIDMISMATCH001` → `MISMATCH`
    - `TESTNIDTIMEOUT001` → `TIMEOUT`
    - `TESTNIDUNAVAIL001` → `PROVIDER_ERROR`
    - Unknown IDs → `NOT_FOUND`
- **Zero Scraping / No Fake Government APIs:** Provider is explicitly labeled `DEVELOPMENT MOCK` in all UI views, logs, and audit trails.

---

## 9. M8 — Cross-Document Intelligence & Relationships

National ID integrates seamlessly into `CrossDocumentVerificationEngine` across peer documents:

### 1. Passport ↔ National ID (`passport_national_id_relationship.py`)
- **Name Consistency:** Token-set normalized matching (`RelationshipType.PERSON_NAME_CONSISTENCY`).
- **DOB / YOB Consistency:**
  - Full DOB ↔ Full DOB: Exact ISO comparison (`MATCHED` or `MISMATCH`).
  - Full DOB ↔ Year-only (YOB):
    - Same year (e.g. `1992` vs `1992-05-15`) → `CONSISTENT_YEAR` (`severity: NONE`).
    - Differing year (e.g. `1995` vs `1996-06-15`) → `MISMATCH` (`severity: HIGH`).
- **Identifier Isolation:** National ID number is NEVER compared against Passport number.

### 2. Driving License ↔ National ID (`dl_national_id_relationship.py`)
- **Name Consistency:** Bearer name comparison.
- **DOB / YOB Consistency:** Full date and partial year consistency validation.

---

## 10. M6 — Risk Engine Integration & Anti-Double-Counting

- **Generic Evidence Consumption:** Risk signals from National ID M2, M5, and M8 pass into the central `RiskAggregator` using standard `RiskEvidenceItem` structures.
- **Correlation Groups (Anti-Double-Counting):**
  - Signals concerning the same underlying defect are mapped to unified correlation groups:
    - `CorrelationGroup.NID_PASSPORT_DOB_CONSISTENCY`
    - `CorrelationGroup.NID_PASSPORT_NAME_CONSISTENCY`
    - `CorrelationGroup.NID_DL_DOB_CONSISTENCY`
    - `CorrelationGroup.IDENTIFIER_VALIDITY`
  - Subsequent signals within the same correlation group decay exponentially (e.g., $0.50 \times$ multiplier), preventing unfair score inflation.
- **Decision Support:** Outputs risk scores and recommendations for officer review. The system makes NO autonomous legal or admissibility decisions.

---

## 11. Strict Privacy & Zero Demographic Profiling

- **Immunity from Demographic Bias:**
  - Demographic fields (`gender`, `address`, `state`, `religion`, `ethnicity`) are **NEVER** assigned risk weights or adverse signals in `RULE_TABLE`.
  - Gender and address are used solely for localized document-to-document consistency when legitimately present.
- **Sensitive Identifier Masking:**
  - The 12-digit National ID is masked in logs, audit records, exception messages, and frontend headers (`XXXX XXXX 1098`).
  - Raw unmasked numbers remain restricted to isolated, encrypted verification sessions.

---

## 12. Security & Anti-Tamper Guarantees

- **Server-Side Enforcement:** Clients cannot submit client-side validation results, risk scores, registry states, or cross-document matches.
- **Sanitized Outputs:** All OCR text is sanitized to neutralize XSS vectors before frontend rendering.
- **Cryptographic Quarantine:** Raw biometric embeddings (ArcFace 512D vectors) are never exposed via public APIs or included in risk evidence JSON.

---

## 13. Case Management & Document Lifecycle

- **Multi-Document Verification Case:** A case can simultaneously manage 4 active documents:
  - `DOC-001`: Passport
  - `DOC-002`: Visa
  - `DOC-003`: Driving License
  - `DOC-004`: National ID
- **Duplicate Document Type Handling:** Uploading a second National ID without the replacement flag triggers `DuplicateDocumentTypeError`.
- **Replacement & Stale Evidence Invalidation:**
  - Replacing a National ID marks the previous document `SUPERSEDED`.
  - All existing cross-document relationships tied to the superseded document are immediately invalidated and purged from case risk calculations.

---

## 14. Supported vs. Unsupported Reference Layouts

| Layout Type | Status | System Action |
| :--- | :--- | :--- |
| Standard UIDAI Aadhaar Physical / Letter Format | Supported | Full M1–M6 analytical pipeline executed |
| UIDAI e-Aadhaar Digital Card | Supported | Full M1–M6 analytical pipeline executed |
| QR Code (Plain XML / JSON / Delimited) | Supported | Decoded payload comparison enabled |
| Severely blurred / degraded card | Inconclusive | `IMAGE_QUALITY_INSUFFICIENT` returned; forensics bypassed safely |
| Foreign National ID Cards | Unsupported | Returns `UNSUPPORTED_PROFILE` with zero hallucinated values |
| Fabricated / Unrecognized Card Designs | Unsupported | Parser signals missing required fields; validation fails safely |

---

## 15. Known Limitations & Future Roadmap

1. **Cryptographic QR Signature Verification:** Currently decodes XML/JSON payloads (`PAYLOAD_DECODED`). Cryptographic verification against UIDAI root certificates is earmarked for Phase 11.
2. **Offline Masked Aadhaar Variant:** Offline cards with pre-masked numbers (`XXXX XXXX 1234`) will have the check-digit calculated over available digits or flagged as partial.
3. **Multi-Lingual OCR:** Indian National IDs feature regional scripts (Hindi, Tamil, Telugu, etc.) alongside English. Current OCR prioritizes English text extraction.
