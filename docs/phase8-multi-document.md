# Multi-Document Verification & Cross-Document Intelligence Architecture

**System:** AI-Based Fake Identity & Document Screening System  
**Version:** `0.8.0-phase8`  
**Status:** Complete  

---

## 1. Executive Summary & Core Architectural Concepts

Phase 8 introduces **Multi-Document Verification** and **Cross-Document Intelligence** to the screening terminal. Rather than treating each document as an isolated session, Phase 8 enables multiple documents belonging to the same traveler or screening incident to be grouped into a single **Verification Case**.

Each document is verified independently through the existing Module 1–Module 6 (M1–M6) pipeline without duplicate analytical engines. Once two or more documents are present within a case, the **CrossDocumentVerificationEngine** executes deterministic cross-document consistency checks and feeds normalized relationship evidence into Module 6 (Risk Engine) with double-counting protection.

### Three Distinct Concepts

1. **Verification Case (`VerificationCase`):**
   The overarching screening session tracking all uploaded documents, evaluation state, relationship evidence, case-level composite risk assessment, and tamper-evident audit trail.
2. **Document Verification (`CaseDocument`):**
   An individual credential (e.g. Passport or Visa) within a case, maintaining its independent M1–M6 analytical results, document ID (`DOC-001`), verification ID, revision, and status.
3. **Document Relationship (`CrossDocumentEvidenceItem`):**
   A structured, deterministic comparison between fields across two documents (e.g. Visa `passport_number` ↔ Passport `document_number`).

```
                    VERIFICATION CASE (CASE-001)
                                │
          ┌─────────────────────┼─────────────────────┐
          ↓                     ↓                     ↓
     Passport (DOC-001)     Visa (DOC-002)       Future Credential
          │                     │                     │
        M1–M5                 M1–M5                 M1–M5
          │                     │                     │
          └──────────┬──────────┘                     │
                     ↓                                │
           Cross-Document Engine                      │
                     │                                │
          Relationship Registry                       │
          (Order-Independent)                         │
                     │                                │
         Field-Level Comparisons                      │
                     │                                │
          Cross-Document Evidence                     │
                     │                                │
                     └────────────────┬───────────────┘
                                      ↓
                         Evidence Deduplication &
                         Double-Counting Protection
                                      ↓
                               Module 6 (Risk)
                                      ↓
                           Officer Decision Support
```

---

## 2. Multi-Document Lifecycle & State Model

### Lifecycle Flow
1. **CREATE CASE:** Initializes a clean case with unique `case_id` (e.g., `CASE-20260906-XXXXXX`) and active status.
2. **ADD DOCUMENT:** Ingests and processes Document A through M1–M5; records `CaseDocument` with revision 1.
3. **PROCESS DOCUMENT:** If only one document exists, single-document workflow and risk assessment operate normally.
4. **ADD PEER DOCUMENT:** Ingests Document B; executes M1–M5 on Document B only (does **not** rerun Document A).
5. **RUN CROSS-DOCUMENT ANALYSIS:** Evaluates all active pairs using registered relationship profiles.
6. **UPDATE COMBINED EVIDENCE:** Aggregates document-level evidence and cross-document evidence into a unified evidence set.
7. **RUN/REFRESH M6:** Evaluates composite case risk with double-counting protection and conflict detection.
8. **OFFICER REVIEW:** Interactive workstation displays document details, relationship consistency, and recommendation.

### Status Separation
- **Document Status (`DocumentStatus`):** `UPLOADED`, `PROCESSING`, `COMPLETED`, `FAILED`, `PARTIAL`, `SUPERSEDED`, `REMOVED`.
- **Case Status (`CaseStatus`):** `ACTIVE`, `PROCESSING`, `READY_FOR_REVIEW`, `COMPLETED`, `ERROR`.

---

## 3. Relationship Registry & Profile Specifications

The `DocumentRelationshipRegistry` maintains bidirectional, order-independent relationship profiles between document pairs:

```python
pv_profile = RelationshipProfile(
    source_document_type="visa",
    target_document_type="passport",
    definitions=[
        RelationshipDefinition(
            source_field="passport_number",
            target_field="document_number",
            relationship_type=RelationshipType.IDENTIFIER_BINDING,
            comparison_mode=ComparisonMode.STRICT,
            severity_on_mismatch=EvidenceSeverity.HIGH,
            correlation_group=CorrelationGroup.PASSPORT_VISA_IDENTIFIER_BINDING,
        ),
        ...
    ],
)
```

### Order Independence
Whether Passport is uploaded first or Visa is uploaded first, `registry.resolve_profile(doc_a, doc_b)` resolves the same canonical profile and maps field comparisons symmetrically.

---

## 4. Field Comparison & Normalization Rules

The `RelationshipComparator` executes deterministic field comparisons:

| Comparison Mode | Rules | Fuzzy Matching? |
| :--- | :--- | :--- |
| **STRICT** | Exact alphanumeric equality after stripping whitespace and non-alphanumeric punctuation (`re.sub(r'[^A-Z0-9]', '', s.upper())`). | **FORBIDDEN**. Identifier comparisons (Passport #, Visa #) are strictly exact. |
| **NORMALIZED_DATE** | Parses ISO dates (`1990-06-15`), MRZ dates (`900615`), and textual formats (`15 JUN 1990`) into canonical `datetime.date` before equality comparison. | Conservative format normalization only. |
| **NORMALIZED_TOKEN_SET** | Case and whitespace normalization with token set comparison. Exact token match = `MATCHED`. Proper subset (e.g. "JOHN DOE" vs "JOHN ALEXANDER DOE") = `PARTIAL_MATCH` (severity LOW, never false fraud). Distinct tokens = `MISMATCH`. | Conservative token comparison only. Aggressive Levenshtein/phonetic fuzzy matching is strictly avoided. |
| **NORMALIZED_CODE** | Canonical 3-letter ICAO/ISO code comparison (e.g. `USA`, `IND`). | Exact code equality. |

---

## 5. Cross-Document Evidence Model

Cross-document evidence items are serialized with full provenance and explainability:

```json
{
  "evidence_id": "XDC-001",
  "relationship_type": "IDENTIFIER_BINDING",
  "source_document": {
    "document_id": "DOC-002",
    "document_type": "visa",
    "field": "passport_number",
    "value": "T9876548"
  },
  "target_document": {
    "document_id": "DOC-001",
    "document_type": "passport",
    "field": "document_number",
    "value": "T9876543"
  },
  "status": "MISMATCH",
  "severity": "HIGH",
  "confidence": 0.99,
  "explanation": "The passport number referenced by the Visa (T9876548) does not match the Passport document number (T9876543)."
}
```

---

## 6. Module 6 Integration & Double-Counting Protection

### Normalized Evidence Interface
Cross-document evidence enters Module 6 as canonical `RiskEvidenceItem`s:
- `module`: `"CROSS_DOCUMENT"`
- `signal`: `"cross_doc_identifier_binding_mismatch"`
- `category`: `EvidenceCategory.DOCUMENT_CONSISTENCY`
- `severity`: `EvidenceSeverity.HIGH`
- `confidence`: `0.99`
- `correlation_group`: `"PASSPORT_VISA_IDENTIFIER_BINDING"`

### Double-Counting Protection Invariant
If a discrepancy is detected by:
1. M2 Visa Validation (`passport_reference_invalid`)
2. M5 Registry (`registry_mismatch` on passport reference)
3. Cross-Document Engine (`cross_doc_identifier_binding_mismatch`)

The system tags all items with the correlation group `PASSPORT_VISA_IDENTIFIER_BINDING`. In `CaseRiskEvaluator._deduplicate_evidence()`, items with the same underlying semantic correlation are deduplicated so the adverse finding is only counted once towards the composite score.

---

## 7. Stale Evidence Protection & Invalidation

When a document inside a case is replaced (superseded) or removed:
- Any relationship referencing that `document_id` is immediately purged from `case.relationships`.
- Any risk evidence referencing that `document_id` is purged from `case.cross_document_evidence`.
- Audit event `RELATIONSHIP_CHANGED` is recorded.
- Case composite risk is automatically recalculated.
- **Guarantee:** No stale relationship evidence can contaminate the active case assessment.

---

## 8. Extensibility: Adding Future Document Types

Adding a third document type (e.g. `DrivingLicense`) requires **zero modifications** to:
- `CrossDocumentVerificationEngine`
- `Module 6 (Risk Engine)`
- `OCR Engine`
- `Forensic Aggregator`
- `Biometric Engine`
- `Registry Engine`

**Only two steps are needed:**
1. Register `DocumentProfile` (e.g. for `driving_license`).
2. Register `RelationshipProfile` (e.g. `driving_license` ↔ `passport`).

This architectural invariant is formally verified by `tests/test_case_extensibility.py`.

---

## 9. API Reference

Mounted under `/api/v1/verification/case`:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/verification/case` | Initialize a new multi-document case |
| `GET` | `/api/v1/verification/case/{case_id}` | Retrieve case summary, documents, relationships, and risk assessment |
| `POST` | `/api/v1/verification/case/{case_id}/documents` | Upload and attach a document (multipart/form-data) |
| `DELETE` | `/api/v1/verification/case/{case_id}/documents/{document_id}` | Remove a document from the case and recalculate risk |
| `POST` | `/api/v1/verification/case/{case_id}/evaluate` | Re-evaluate cross-document relationships across all active peers |
| `POST` | `/api/v1/verification/case/risk` | Compute or refresh case-level composite risk assessment |

---

## 10. Frontend Workstation Reference

- **Enterprise Theme:** Modern, light, accessible security workstation (no dark cyberpunk/neon aesthetics).
- **Mode Toggle:** Instant switching between "Single Document Mode" (preserving single-document workflows) and "Multi-Doc Case (Phase 8)".
- **Case Documents List (`CaseDocuments.jsx`):** Document cards with status badges for M1 through M6, revision number, active inspection selection, and removal.
- **Add Document Modal (`AddDocumentModal.jsx`):** Modal displaying Passport and Visa as Available, and Driving License, National ID, Border Permit as Coming Soon.
- **Cross-Document Consistency Table (`CrossDocumentPanel.jsx`):** Field-by-field value comparison, status badges (`MATCHED`, `MISMATCH`, `PARTIAL_MATCH`), severity indicators, and explanations.
- **Composite Risk Card (`CaseRiskSummary.jsx`):** Score dial, risk level, officer recommendation, conflict alert banner, and statutory decision support disclaimer.

---

## 11. Security & Operational Constraints

1. **Server-Side Evaluation Guarantee:** The client cannot submit arbitrary relationship outcomes. All relationship statuses and risk scores are deterministically computed on the server.
2. **PII and Privacy:** Cross-document relationships store targeted field references and comparisons rather than whole duplicated dossiers. No biometric face embeddings are stored in cross-document evidence.
3. **No Autonomous Final Decision:** Case-level outputs provide structured reasons, conflict alerts, and advisory recommendations (`STANDARD OFFICER REVIEW`, `HIGH PRIORITY REVIEW`, etc.). Final screening decisions are strictly reserved for authorized officers.
