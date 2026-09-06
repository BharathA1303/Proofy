# Phase 5 — Generic Registry Verification Engine

## Module: 5 — Registry Verification Engine
**Status:** Implemented (Development Sandbox Mode)  
**Version:** 0.5.0-phase5  
**Upstream:** Modules 1–4 (OCR, Validation, Forensics, Biometrics)  
**Downstream:** Module 6 (Risk Engine — pending)

---

## Overview

Module 5 verifies whether identity information extracted and validated by Modules 1–4 corresponds to a record in an authoritative registry or authorized verification source.

**This is NOT a database lookup.** It is a Generic Registry Verification Engine designed to support:

| Document Type | Status | Provider |
|---|---|---|
| Passport | ✅ Implemented | Development Mock |
| Visa / Stamp | Stubbed (UNAVAILABLE) | — |
| Driving License | Stubbed (UNAVAILABLE) | — |
| National ID | Stubbed (UNAVAILABLE) | — |
| Border Permit | Stubbed (UNAVAILABLE) | — |

> [!IMPORTANT]
> **Development Sandbox Only.** The current implementation uses a clearly-labeled development mock provider. It is NOT connected to any real government database. `source_type: "development_mock"` is always visible in every response.

---

## Architecture

```
POST /api/v1/verification/registry
         │
   RegistryEngine (engine.py)
         │
   RegistrySessionStore ──── populated at /ocr time
         │
   ProviderResolver (resolver.py)
         │
   ┌─────┴──────────────────────────────┐
   ▼                                    ▼
PassportRegistryAdapter          (future adapters)
   │
MockPassportRegistryProvider
   │
RegistryComparator → RegistryFieldResult[] → RegistryStatus
```

### Key Design Principles

1. **Generic, not passport-only.** All document types are supported at the engine level. Only the provider is type-specific.

2. **No client-submitted identity data.** The `/registry` endpoint accepts only `verification_id` + `document_type`. All identity data is retrieved server-side from `RegistrySessionStore`, populated during the `/ocr` step.

3. **Evidence, not verdict.** Module 5 produces `RegistryStatus` (MATCHED / NOT_FOUND / MISMATCH / REVOKED / EXPIRED / etc.). It never produces `risk_score`, `final_decision`, or fraud verdicts — those belong to Module 6.

4. **Provider failures ≠ document fraud.** UNAVAILABLE / TIMEOUT are clearly distinct from NOT_FOUND or MISMATCH in the evidence.

5. **Strict document number matching.** No Levenshtein or fuzzy matching for the primary document identifier. One-digit-off is MISMATCH, never MATCHED.

---

## API

### `POST /api/v1/verification/registry`

**Request body:**
```json
{
  "verification_id": "uuid-from-ocr-step",
  "document_type": "passport"
}
```

**Response:**
```json
{
  "verification_id": "string",
  "document_type": "passport",
  "registry": {
    "provider": "mock-passport-registry-v1",
    "status": "MATCHED",
    "record_found": true,
    "registry_document_status": "ACTIVE"
  },
  "field_results": [
    {
      "field": "document_number",
      "document_value": "TESTPASS001",
      "registry_value": "TESTPASS001",
      "status": "MATCH",
      "is_critical": true,
      "note": null
    }
  ],
  "evidence": [...],
  "provider_metadata": {
    "provider_id": "mock-passport-registry-v1",
    "source_type": "development_mock",
    "response_time_ms": 9.2
  },
  "audit": {
    "verification_id": "string",
    "timestamp": "2026-09-06T07:22:16Z",
    "document_type": "passport",
    "provider_id": "mock-passport-registry-v1",
    "source_type": "development_mock",
    "registry_status": "MATCHED",
    "record_found": true,
    "response_time_ms": 9.2,
    "disclaimer": "DEVELOPMENT MOCK DATA — not a real government registry result."
  }
}
```

---

## Registry Status Decision Tree

| Condition | Status |
|---|---|
| Provider unreachable | `UNAVAILABLE` |
| Provider timeout | `TIMEOUT` |
| Authentication failure | `AUTHENTICATION_ERROR` |
| Provider-side error | `PROVIDER_ERROR` |
| No record found | `NOT_FOUND` |
| Registry says REVOKED | `REVOKED` |
| Registry says SUSPENDED | `SUSPENDED` |
| Registry says EXPIRED | `EXPIRED` |
| Registry says INVALID | `INVALID` |
| Critical field mismatch | `MISMATCH` |
| All critical fields match | `MATCHED` |
| Partial comparable data | `INCONCLUSIVE` |

---

## Critical Fields (Passport)

| Field | Priority | Comparison Method |
|---|---|---|
| document_number | Critical | Strict equality (normalized) |
| date_of_birth | Critical | Date normalization + equality |
| name | Critical | Token-set comparison (no fuzzy) |
| nationality | Critical | Uppercase + MRZ filler strip |
| expiry_date | Secondary | Date normalization + equality |
| issuing_authority | Secondary | Case-insensitive equality |

---

## Development Mock Records

| Document Number | Registry Status | Expected M5 Status |
|---|---|---|
| `TESTPASS001` | ACTIVE | `MATCHED` (with matching data) |
| `TESTEXPIRED001` | EXPIRED | `EXPIRED` |
| `TESTREVOKED001` | REVOKED | `REVOKED` |
| `TESTMISMATCH001` | ACTIVE | `MISMATCH` (name/DOB/nationality differ) |
| `TESTSUSPENDED001` | SUSPENDED | `SUSPENDED` |
| (any other) | — | `NOT_FOUND` |

---

## Session Store

Registry session data is stored in `RegistrySessionStore` at `/ocr` time:
- **TTL:** 15 minutes (configurable via `REGISTRY_SESSION_TTL_SECONDS`)
- **Thread-safe:** Yes (uses `threading.Lock`)
- **Bounded:** 100 entries max (LRU-evicts oldest)
- **Privacy:** Ephemeral, in-memory only — never written to disk

---

## Configuration

```env
REGISTRY_PROVIDER_MODE=mock
REGISTRY_PROVIDER_PASSPORT=mock
REGISTRY_PROVIDER_VISA=mock
REGISTRY_PROVIDER_DL=mock
REGISTRY_PROVIDER_NATIONAL_ID=mock
REGISTRY_PROVIDER_BORDER_PERMIT=mock
REGISTRY_CONNECT_TIMEOUT=5.0
REGISTRY_READ_TIMEOUT=10.0
REGISTRY_TOTAL_TIMEOUT=15.0
REGISTRY_MAX_RETRIES=1
REGISTRY_SESSION_TTL_SECONDS=900
```

---

## Plugging in an Authorized Provider (Future)

1. Create `providers/authorized_passport.py` implementing `RegistryProvider`
2. Set `REGISTRY_PROVIDER_PASSPORT=authorized_api` in environment
3. Implement `verify()` using the government API credentials (from secret manager)
4. Update `ProviderResolver._create_provider()` to instantiate the new class

**Zero changes** to the engine, comparator, schemas, or frontend are required.

---

## Frontend Integration

### Trigger
M5 fires automatically after M4 (face verification) completes, in `BiometricStatus.jsx`.

### State
- `session.registryDetail` — full `RegistryVerificationResponse`
- `session.checks.registryVerification` — `passed | warning | failed`

### Display
- `VerificationChecks.jsx` — expand button on M5 row when `registryDetail` is available
- `RegistryStatus.jsx` — evidence panel showing field comparison, status banner, provider metadata

### UI Rules
- `source_type = 'development_mock'` → displays "Development Sandbox" badge
- Never displays "Government Verified" in sandbox mode
- Never displays CLEARED / DENIED / risk scores

---

## File Inventory

### Backend — New Files

| File | Purpose |
|---|---|
| `app/schemas/registry.py` | Pydantic v2 schemas and enums |
| `app/services/registry/__init__.py` | Package init |
| `app/services/registry/base.py` | Abstract `RegistryProvider` |
| `app/services/registry/normalizers.py` | Name/date/docnum normalization |
| `app/services/registry/comparator.py` | Field comparison + decision tree |
| `app/services/registry/session_store.py` | TTL-bounded session store |
| `app/services/registry/resolver.py` | `document_type → provider` routing |
| `app/services/registry/engine.py` | Orchestrator — main entry point |
| `app/services/registry/adapters/__init__.py` | Adapters package init |
| `app/services/registry/adapters/passport_adapter.py` | Passport field extraction |
| `app/services/registry/providers/__init__.py` | Providers package init |
| `app/services/registry/providers/mock_passport.py` | Development mock provider |

### Backend — Modified Files

| File | Change |
|---|---|
| `app/schemas/registry.py` | New file |
| `app/core/exceptions.py` | +7 registry exceptions |
| `app/core/config.py` | +9 registry config fields, version bump |
| `app/api/v1/verification.py` | +`/registry` endpoint, +session store population in `/ocr`, +imports |
| `app/main.py` | Updated description |

### Backend — Tests

| File | Coverage |
|---|---|
| `tests/test_registry_normalizers.py` | Name, date, docnum, nationality normalization |
| `tests/test_registry_comparator.py` | Field comparison + all decision tree paths |
| `tests/test_mock_passport_provider.py` | Provider lifecycle + all 5 test records |
| `tests/test_registry_engine.py` | Session not found, provider unavailable, exception mapping |
| `tests/test_registry_api.py` | API endpoint: all statuses, validation, audit trail, source_type |

### Frontend — New Files

| File | Purpose |
|---|---|
| `src/components/registry/RegistryStatus.jsx` | Evidence panel component |
| `src/components/registry/RegistryStatus.module.css` | Component styles |

### Frontend — Modified Files

| File | Change |
|---|---|
| `src/state/verification/initialState.js` | +`registryDetail: null` |
| `src/state/verification/verificationReducer.js` | +`SET_REGISTRY_DETAIL` action |
| `src/state/verification/VerificationContext.jsx` | +`setRegistryDetail` dispatcher |
| `src/services/verificationApi.js` | +`runRegistryVerification()` |
| `src/components/biometric/BiometricStatus.jsx` | M5 auto-triggered after M4 |
| `src/components/verification/VerificationChecks.jsx` | Registry evidence panel |

---

## What Module 6 Will Receive

When Module 6 (Risk Engine) is implemented, it will receive:
- `M1` — OCR extraction confidence
- `M2` — Checksum results + VIZ-MRZ binding
- `M3` — Forensic signals (ELA, photo boundary, etc.)
- `M4` — Face match similarity + liveness score
- **`M5`** — `RegistryStatus` + field-level results + evidence

The Risk Engine will combine these signals into a `risk_score` and `final_decision`. Module 5 deliberately outputs no verdict of its own.
