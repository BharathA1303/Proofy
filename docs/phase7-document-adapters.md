# Generic Document Adapter Framework & Visa Implementation Architecture

**System:** AI-Based Fake Identity & Document Screening System  
**Version:** `0.7.0-phase7`  
**Status:** Complete  

---

## 1. Executive Summary & Generic Architecture

The Phase 7 implementation establishes a **document-agnostic architecture** for border and identity screening. Previously, Modules 1–6 (M1–M6) operated with Passport as the reference implementation. Phase 7 achieves two primary goals:
1. **Strengthens the generic framework** so that the screening pipeline operates across arbitrary identity credentials without hardcoded document assumptions.
2. **Implements Visa as the first true second document type**, demonstrating multi-document versatility while preserving the exact mathematical invariants of M1–M6.

### Core Architectural Principle

Rather than duplicating parallel silos (`visa_ocr.py`, `visa_validation.py`, `visa_risk.py`, etc.), the system enforces a single canonical pipeline:

```
                         Verification Pipeline
                                  │
                       Document Profile Registry
                                  │
             ┌────────────────────┴────────────────────┐
             ↓                                         ↓
      Passport Profile                            Visa Profile
             │                                         │
     Passport Adapters                           Visa Adapters
             │                                         │
             └────────────────────┬────────────────────┘
                                  ↓
                       Normalized Evidence Model
                                  ↓
                        Common M1–M6 Engines
                      (OCR, Val, For, Bio, Reg, Risk)
                                  ↓
                       Officer Decision Support
```

**Non-duplication Guarantee:**
- Common OCR extraction engine is reused.
- Forensic analysis (ELA, compression, metadata, image quality) is reused.
- Biometric pipeline (SCRFD/Haar, ArcFace embeddings, MiniFASNet PAD) is reused.
- Registry verification engine (deterministic comparator, status mapping) is reused.
- Risk engine (Module 6: rule table, score aggregator, conflict detector, explanation builder) has **zero** document-specific branching or scoring formulas.

---

## 2. Document Profile System & Registry

### Profile Specification (`DocumentProfile`)
Each document type is declared as an immutable `DocumentProfile` dataclass specifying:
- `document_type`: Canonical machine key (`passport`, `visa`, `driving_license`, etc.)
- `display_name`: Human-readable label (`Passport`, `Visa`, etc.)
- `status`: Operational availability (`available`, `coming_soon`, `not_implemented`)
- `mrz_applicable`: Whether MRZ lines are expected (True for TD3 passports, False/optional for visas)
- `portrait_required`: Whether biometric facial portrait is required for valid credentials
- `linked_document_fields`: External document references (e.g., Visa references Passport Number)
- `supported_modules`: Explicit support map across `ocr`, `validation`, `forensics`, `biometrics`, `registry`, `risk`

### Document Profile Registry (`DocumentProfileRegistry`)
The central registry (`backend/app/services/documents/profiles/document_profile_registry.py`) provides:
- **Profile Registration:** Deterministic registration of profiles with conflict detection.
- **Alias Resolution:** Resolves input strings (e.g., `'visa'`, `'visa_stamp'`, `'visas'`) to canonical profiles.
- **Operational Enforcement:** Rejects unoperational profiles (`coming_soon`) with HTTP 422 (`UnsupportedDocumentTypeError`) and unrecognised documents with HTTP 404 (`UnknownDocumentTypeError`).
- **Startup Integrity Validation:** Validates on application boot that all profiles are well-formed and compliant.

```python
profile = document_profile_registry.resolve("visa")
document_profile_registry.ensure_operational("visa")
```

---

## 3. Implemented Document Profiles

| Document Type | Status | MRZ Applicable | Portrait Required | Key Security Standards |
|---|---|---|---|---|
| **Passport** | `available` | Yes (TD3) | Yes (Mandatory) | ICAO Doc 9303 Part 4, MRZ check digits, VIZ binding |
| **Visa** | `available` | Optional / No | No (Optional) | ICAO Doc 9303 Part 7, visa number formats, dates, linked passport reference |
| **Driving License** | `coming_soon` | No | Yes | ISO/IEC 18013-1 (Reserved for Phase 8) |
| **National ID** | `coming_soon` | Yes (TD1) | Yes | ICAO Doc 9303 Part 5 (Reserved for Phase 8) |
| **Border Permit** | `coming_soon` | No | No | UN ECE Transit Protocol (Reserved for Phase 8) |

---

## 4. Adapter Interfaces & Module Routing

### M1: OCR Routing
- The API endpoint `POST /api/v1/verification/ocr` resolves the document type via `document_profile_registry`.
- The common image ingestion and preprocessing pipelines run uniformly.
- High-level text and bounding boxes are extracted via PaddleOCR.
- Based on profile, parsing is dispatched to `PassportParser` or `VisaParser`.
- Visa parsing extracts: `docNumber` (Visa #), `passportNumber`, `name`, `nationality`, `dob`, `visaType`, `issuedDate`, `expiry`, `entries`, `durationOfStay`, and `authority`.

### M2: Validation Routing
- Dispatches to `validate_visa_document` via `VisaValidator`.
- Evaluates:
  - Required field presence (name, visa number, expiry date, issued date, nationality).
  - Format checking on visa identifiers.
  - Chronological consistency: `issue_date <= expiry_date` and `dob <= issue_date`.
  - Expiry status: verifies document is current.
  - No blind ICAO TD3 checksums are enforced for Visa unless explicitly defined by format.
  - Cross-document passport reference validation.

### M3: Forensics Routing
- Reuses the shared forensic engine (`ForensicService`).
- Runs Error Level Analysis (ELA), JPEG compression grid analysis, metadata inspection, and sharpness/contrast assessment.
- For portrait regions, if no reliable photo boundary is detected or portrait is not defined for the visa profile, the engine records `status=insufficient_data` or `no_reliable_candidate` rather than fabricating regions or declaring forgery.

### M4: Biometrics Routing
- If portrait is unavailable or not applicable on the Visa profile, M4 evaluates to `NOT_APPLICABLE` or `DOCUMENT_FACE_UNAVAILABLE`.
- When a usable portrait is present, M4 executes the full YuNet/SCRFD face detector, MiniFASNet anti-spoofing, and ArcFace cosine matching against the live capture.

### M5: Registry Verification Routing
- `RegistryEngine` delegates request synthesis to `VisaRegistryAdapter`, mapping session store fields to `RegistryVerificationRequest`.
- In development, the request resolves to `MockVisaRegistryProvider` (`source_type: "development_mock"`).
- Uses deterministic records (`TESTVISA001`, `TESTVISAEXPIRED001`, `TESTVISAREVOKED001`, `TESTVISAMISMATCH001`, `TESTVISASUSPENDED001`, etc.).
- Normalizes comparisons via generic `compare_fields` decision tree.

### M6: Risk Engine Normalization
- M6 (`RiskEngine`, `RiskAggregator`, `ConflictDetector`, `ExplanationBuilder`) contains **zero** document-specific code paths.
- All M1–M5 outputs are normalized into canonical `RiskEvidenceItem` objects.
- Both Passport and Visa evidence enter the exact same risk rule table and score aggregation formula:
  $$\text{Total Score} = \min\left(\sum \text{Category Contributions}, 100\right)$$

---

## 5. Cross-Document Relationships

Visas typically reference the bearer's travel passport number. The architecture models this via the generic `DocumentRelationship` structure:

```json
{
  "relationship_type": "passport_reference",
  "source_document": "visa",
  "source_field": "passport_number",
  "target_document": "passport",
  "target_field": "document_number",
  "status": "MATCHED" | "MISMATCH" | "UNAVAILABLE"
}
```

- When both documents are submitted, `evaluate_visa_passport_relationship` compares the normalized values.
- If values mismatch, it produces a `cross_document_mismatch` signal with `EvidenceSeverity.CRITICAL`.
- This signal feeds into canonical M2 validation evidence and is scored by the generic M6 risk aggregator without specialized visa logic.
- If the Passport document is not present, the relationship status evaluates to `UNAVAILABLE` without penalizing the traveler.

---

## 6. Unsupported & Coming Soon Documents

Unsupported document types (`driving_license`, `national_id`, `border_permit`) are strictly prevented from entering fake or half-baked pipelines:
- **API Guard:** Attempting to invoke verification endpoints with unsupported types returns HTTP 422:
  ```json
  {
    "detail": "This document type is not yet supported for verification."
  }
  ```
- **Frontend Guard:** Document tabs display distinct `"Soon"` badges and have disabled pointer events and `aria-disabled="true"`.
- **Metadata API:** `GET /api/v1/documents/profiles` surfaces the live status of all registered documents for dynamic UI configuration.

---

## 7. Future Document Extension Procedure

To add a new document type (e.g. **Driving License**) in the future:
1. **Create Profile:** Create `backend/app/services/documents/profiles/driving_license_profile.py` inheriting from `DocumentProfile` with `status=available`.
2. **Implement Parser & Validator:** Implement `DLParser` and `DLValidator` in `backend/app/services/documents/driving_license/`.
3. **Register Profile:** Register the profile in `DocumentProfileRegistry`.
4. **Implement Registry Adapter:** Create `DrivingLicenseRegistryAdapter` mapping session data to `RegistryVerificationRequest`.
5. **Add Fixtures & Tests:** Add unit tests for parser, validator, and registry lookups.
6. **Zero M6 Changes:** Do **NOT** modify `RiskEngine`, `RiskAggregator`, or risk formulas; map validator signals to canonical `RiskEvidenceItem`s.

---

## 8. Security Considerations

1. **Untrusted OCR Input:** Text and bounding boxes extracted from documents are treated as untrusted user input. Strings are normalized and HTML-escaped before rendering in frontend components.
2. **No Client-Side Scoring:** All risk assessment, validation checks, and registry statuses are computed strictly on the backend. The frontend cannot inject or override verification results.
3. **Mock Provider Identification:** All mock providers prominently output `source_type: "development_mock"` and non-government notices. No fake government authenticity is ever asserted.
4. **Data Isolation:** Session stores partition verification sessions by cryptographically generated UUIDs.
