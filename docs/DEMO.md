# SIH Demonstration Guide & Scenarios

**Project:** AI-Based Fake Identity & Document Screening System  
**Version:** `1.0.0-phase12`  
**Target Audience:** Smart India Hackathon (SIH) Evaluators & Jury  

---

## 1. System Orientation for Evaluators

Before demonstrating test cases, highlight the core philosophy:
1. **Decision Support, Not Autonomous Enforcement:** The platform does not autonomously deny or admit travelers; it computes an explainable composite risk evaluation to support authorized human officers.
2. **Document-Agnostic Architecture:** All 5 document profiles (Passport, Visa, Driving License, National ID, Border Permit) run through the identical modular pipeline.
3. **Zero PII on Blockchain:** Only canonical cryptographic SHA-256 evidence digests are anchored on-chain.
4. **Demonstration Environment:** All registry records and blockchain blocks are clearly badged as `DEMONSTRATION / SANDBOX MODE` for evaluation integrity.

---

## 2. Walkthrough Scenarios

### Scenario A — Standard Clean Clearance (Passport + Visa)
**Objective:** Prove seamless multi-document verification, cross-document intelligence, and normal clearance flow.
1. Switch to **Multi-Doc Case (M1–M12)** mode.
2. Click **New Case** to generate a fresh case ID (`CASE-SIH-001`).
3. Click **Add Document** $\to$ Select `Passport` $\to$ Upload standard clean passport image.
   - M1 OCR extracts MRZ lines and identity fields.
   - M2 Validates ICAO Doc 9303 checksums.
   - M3 Confirms normal forensic compression.
   - M4 Matches face crop against live camera feed.
   - M5 Confirms active record in reference sandbox.
4. Click **Add Document** $\to$ Select `Visa` $\to$ Upload matching visa image.
   - Cross-document engine compares `passport_number`, `name`, `date_of_birth`, and `nationality`.
   - All relationships evaluate to `MATCHED`.
5. **Outcome:** Composite Risk is **LOW (Score < 20)**. Automated recommendation: `CLEAR / ADMIT`.
6. Inspect the **Cryptographic Evidence Integrity** panel:
   - Status: `✓ Chain Valid`.
   - Click **Verify Cryptographic Integrity** $\to$ Recomputed SHA-256 matches the anchored block.
7. Officer records authoritative action: Select `ADMIT / CLEAR` $\to$ Click **Commit Decision to Cryptographic Ledger**.

---

### Scenario B — Forensic Tampering Detection (Photo Substitution)
**Objective:** Prove deep forensic analysis detects image manipulation that bypasses visual inspection.
1. In single or case mode, upload a passport with a swapped photograph or altered metadata.
2. **Forensic Signal:** Module 3 flags `ela_anomaly` and `photo_boundary_discontinuity` with `HIGH` severity.
3. **Outcome:** Case risk elevates immediately to **MEDIUM / HIGH (REQUIRES_REVIEW)**.
4. Officer reviews forensic heatmap overlay, confirms localized compression variance, and selects `REFER TO SECONDARY INSPECTION` with reason: *"Suspected physical photo substitution"*.
5. The decision and forensic evidence hash are anchored to the blockchain.

---

### Scenario C — Cross-Document Identity Conflict (Passport ↔ Visa)
**Objective:** Demonstrate that fraudulent credentials paired together fail cross-document binding.
1. Initialize a new case and upload a valid Passport (`document_number = P1234567`).
2. Attach a Visa issued to the same person's name but referencing a different passport number (`passport_number = P9999999`).
3. **Cross-Document Engine:** Detects `IDENTIFIER_BINDING` conflict.
4. **Outcome:** Generates a `MISMATCH` relationship with `HIGH` severity.
5. Conflict detector flags `conflict_detected: true`, raising the composite risk score.
6. Officer inspects the Cross-Document Consistency Table, views the mismatch, and records `REFER TO SECONDARY INSPECTION`.

---

### Scenario D — Registry Outage Graceful Degradation
**Objective:** Prove the system does not crash or falsely accuse travelers when external registries are unreachable.
1. Upload a document when the mock registry provider is offline or returns `UNAVAILABLE`.
2. **Outcome:** Module 5 outputs `status: UNAVAILABLE` with `confidence: 0.0`.
3. The pipeline continues smoothly to M6. The risk engine handles missing evidence gracefully without double-counting or treating missing data as confirmed fraud.
4. Officer Decision Panel advises: *"Missing registry evidence; manual confirmation required."*
5. Officer selects `REQUEST ADDITIONAL DOCUMENTS`.

---

### Scenario E — Blockchain Cryptographic Tamper Detection
**Objective:** Mathematically prove that no evidence or officer decision can be altered after the fact.
1. Complete any case verification.
2. In the **Cryptographic Evidence Integrity** panel, observe the anchored block hash.
3. Execute the tamper simulation test (`python -m pytest tests/test_sih_demo_scenarios.py -k test_scenario_e`):
   - A malicious actor modifies a database record offline, changing a `SUSPICIOUS` finding to `VALID`.
   - The user clicks **Verify Cryptographic Integrity**.
4. **Outcome:** The system recalculates the SHA-256 canonical digest, detects that:
   $$\text{Current Hash } \neq \text{Anchored Block Hash}$$
   and flashes **`INTEGRITY_FAILURE`** with the exact mismatch details!
