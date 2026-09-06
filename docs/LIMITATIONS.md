# Platform Limitations, Edge Cases & Operational Disclaimers

**Platform:** AI-Based Fake Identity & Document Screening System  
**Version:** `1.0.0-phase12`  
**Classification:** Operational Governance & Ethical AI Disclaimers  

---

## 1. Prototype & Sandbox Boundaries

1. **Demonstration Environment:**
   All registry queries connect to an in-memory development mock database. The platform makes **no claim of direct production connection to government databases** (e.g., UIDAI, Parivahan, or national immigration registries).
2. **Local Cryptographic Ledger:**
   The blockchain ledger implementation is a local, permissioned SHA-256 hash-chain designed for auditable demo execution. It is **not a public decentralized cryptocurrency network or an official government sovereign blockchain**.

---

## 2. Non-Autonomous Decision Model

The system is engineered strictly as **decision-support software**:
- Automated risk scores and category classifications are advisory.
- The platform **cannot and does not** issue binding legal determinations (such as statutory deportation, entry refusal, or citizenship determination).
- The final operational action must be executed by an authorized, credentialed human officer.

---

## 3. Computer Vision & Sensor Constraints

1. **Optical Capture Quality:**
   - Images captured under extreme glare, low ambient illumination (< 50 lux), or severe perspective skew (> 35° tilt) may degrade PaddleOCR extraction accuracy.
   - For optimal results, documents should be laid flat under diffuse light.
2. **2D Presentation Attack Detection (PAD):**
   - MiniFASNet evaluates 2D textural patterns and moiré artifacts to detect printed paper masks and digital display replay attacks.
   - It is not a substitute for active 3D depth sensors, structured infrared projectors, or thermal imaging hardware.
3. **Ghost Photo & UV Features:**
   - Standard consumer webcams operate in the visible spectrum (RGB). Inspection of genuine physical UV security threads, holograms, and infrared ink requires specialized multi-spectral border scanners.

---

## 4. Ethical AI & Anti-Profiling Invariant

The M6 Risk Engine incorporates strict algorithmic fairness safeguards:
- Risk calculations rely exclusively on objective document integrity signals (checksums, optical forensics, biometric similarity metrics, and cross-document field bindings).
- **Prohibited Attributes:** The platform strictly prohibits demographic profiling. Attributes such as race, ethnicity, religion, gender, nationality, or political affiliation are **never** utilized as weighted risk factors.
