# Initial Visa Reference Profile Specification

**Document Type:** Visa / Visa Stamp  
**Profile Version:** `0.7.0-phase7`  
**Standard Reference:** ICAO Doc 9303 Part 7 (MRV) & Standard Consular Visas  

---

> [!IMPORTANT]
> **Explicit Scope & Non-Claims Notice:**  
> This is an **initial Visa reference profile** and does **not** represent universal Visa formats worldwide.
> Visa layouts, security devices, machine-readable specifications, and biometric portrait conventions vary significantly across issuing nations, visa classes, consular posts, and e-visa regimes.
> This system makes no claim of production government verification, universal visa authenticity detection, or official government integration.

---

## 1. Field Schema & Normalization

The initial reference profile extracts and normalizes the following canonical traveler and visa identity fields:

| Field Key | Label | Necessity | Parsing Strategy | Normalization Applied |
|---|---|---|---|---|
| `docNumber` | Visa Number | Required | OCR label matching (`Visa No`, `Control #`, `V[0-9]{8}`) | Stripped whitespace, uppercase alphanumeric |
| `passportNumber` | Linked Passport Number | Optional / Contextual | Label matching (`Passport No`, `PPT No`, `Bearer Passport`) | Alphanumeric normalization |
| `name` | Bearer Full Name | Required | Surname + Given Names or Single Name label match | Uppercase, single space separated |
| `dob` | Date of Birth | Optional | Date regex (`YYYY-MM-DD`, `DD/MM/YYYY`, `DD.MM.YYYY`) | Canonical ISO-8601 (`YYYY-MM-DD`) |
| `nationality` | Nationality | Required | 3-letter ISO-3166 alpha-3 or common country name | Normalized country code / name |
| `visaType` | Visa Category / Class | Required | Label matching (`Class`, `Type`, e.g. `B1/B2`, `TOURIST`) | Preserves slashes for visa subcategories |
| `issuedDate` | Issue Date | Required | Date parsing | Canonical ISO-8601 (`YYYY-MM-DD`) |
| `expiry` | Expiration Date | Required | Date parsing | Canonical ISO-8601 (`YYYY-MM-DD`) |
| `entries` | Number of Entries | Optional | Label matching (`Entries`, `M`, `S`, `1`, `2`) | Normalized code (`M` for multiple, integer) |
| `durationOfStay` | Duration of Stay | Optional | Label matching (`Duration`, `Days`) | Formatted duration string |
| `authority` | Issuing Authority | Optional | Label matching (`Embassy`, `Consulate`, `Authority`) | Cleaned uppercase text |
| `mrz` | Machine Readable Visa Lines | Optional | Two lines of 36 chars (MRV-B) or 44 chars (MRV-A) | Formatted MRZ string if present |

---

## 2. Structural Validation Rules

The `VisaValidator` executes structural checks without copying ICAO TD3 passport checksum logic blindly:

1. **Required Fields Check:**
   - Evaluates whether mandatory fields (`name`, `docNumber`, `issuedDate`, `expiry`, `nationality`) are populated.
2. **Identifier Format Check:**
   - Validates that the Visa number adheres to minimum alphanumeric length requirements (at least 6 characters).
3. **Chronology Checks:**
   - `issuedDate <= expiry`: Verifies validity period chronology.
   - `dob <= issuedDate`: Flags impossible timeline where document was issued before birth.
4. **Expiration Status Check:**
   - Determines whether the visa expiration date is before the current screening date.
5. **Cross-Document Passport Check:**
   - If a related passport number is available from the traveler session, compares `visa.passport_number` against `passport.document_number`.
   - Matching returns `passed`.
   - Mismatch returns `failed` with an adverse evidence signal `cross_document_mismatch`.

---

## 3. Forensic & Biometric Considerations

- **Forensic Regions (M3):** Error Level Analysis (ELA) and JPEG compression analysis inspect the entire document image. When photo boundary detection identifies no distinct portrait boundary, the region is reported as `no_reliable_candidate` rather than fabricating coordinates.
- **Biometrics (M4):**
  - Many visas (such as entry stamps or e-visas) do not feature a biometric facial portrait.
  - When portrait detection yields 0 faces, M4 returns status `NOT_APPLICABLE` with explanation:
    `"No usable portrait region was identified for this Visa profile."`
  - When a valid facial portrait is detected on the visa, standard ArcFace facial verification against the live capture proceeds automatically.

---

## 4. Development Mock Registry Sandbox

The Visa registry adapter connects to a deterministic development mock sandbox (`MockVisaRegistryProvider`):

- **Provider ID:** `mock_visa_registry`
- **Source Type:** `development_mock` (visibly surfaced to UI and API responses)
- **Deterministic Test Records:**
  - `TESTVISA001`: `ACTIVE` (Status: `MATCHED`)
  - `TESTVISAEXPIRED001`: `EXPIRED` (Status: `EXPIRED`)
  - `TESTVISAREVOKED001`: `REVOKED` (Status: `REVOKED`)
  - `TESTVISASUSPENDED001`: `SUSPENDED` (Status: `SUSPENDED`)
  - `TESTVISAMISMATCH001`: Field mismatch on name (Status: `MISMATCH`)
  - `TESTVISATIMEOUT001`: Simulates network timeout (Status: `TIMEOUT`)
  - `TESTVISAUNAVAIL001`: Simulates provider downtime (Status: `UNAVAILABLE`)
  - Unregistered numbers: Evaluates to `NOT_FOUND`
