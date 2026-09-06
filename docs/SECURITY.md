# Security & Privacy Architecture

**Platform:** AI-Based Fake Identity & Document Screening System  
**Version:** `1.0.0-phase12`  
**Classification:** Defensive Security & Privacy by Design  

---

## 1. Zero PII on Blockchain Policy

The platform operates under a non-negotiable architectural separation between active verification storage and immutable ledger auditing:

| Data Class | Local Secure Storage (Off-Chain) | Blockchain Audit Ledger (On-Chain) |
|---|---|---|
| Traveler full facial photograph | Stored temporarily in ephemeral session | **STRICTLY PROHIBITED** |
| 512-dimensional ArcFace vectors | Volatile memory only (never serialized) | **STRICTLY PROHIBITED** |
| Document image crops | In-memory BGR numpy / session disk cache | **STRICTLY PROHIBITED** |
| Raw OCR text & addresses | Ephemeral document session | **STRICTLY PROHIBITED** |
| Traveler date of birth / name | Masked traveler summary in UI | **STRICTLY PROHIBITED** |
| Normalized evidence digests | Structured JSON record | **Canonical SHA-256 Hash Only** |
| Officer decision & reason | Encrypted audit database | **Anchored Event + Hash Digest** |

Any attempt to anchor raw image bytes or unmasked biometric representations to the ledger is prevented at the schema validation layer.

---

## 2. Ingestion & File Security Hardening

To prevent Remote Code Execution (RCE) and Denial of Service (DoS) via malicious document uploads:

1. **Decompression Bomb Protection:**
   Pillow's decompression limit is strictly capped at `Image.MAX_IMAGE_PIXELS = 50_000_000` to prevent memory exhaustion from zip bombs or hyper-compressed TIFF/PNG images.
2. **Magic-Byte Signature Verification:**
   Client-supplied `Content-Type` headers are never trusted. The ingestion layer reads file magic bytes directly:
   - JPEG: `\xff\xd8\xff`
   - PNG: `\x89PNG\r\n\x1a\n`
   - WEBP: `RIFF....WEBP`
3. **Payload Size Enforcement:**
   Strict 10MB ceiling enforced via `settings.MAX_FILE_SIZE_MB = 10`. Oversized uploads are rejected prior to memory decoding.
4. **Safe Temporary File Handling:**
   All temporary files are created with unique UUID prefixes within an isolated sandbox and cleaned up automatically upon session completion.

---

## 3. Cryptographic Tamper Evidence

The audit ledger maintains an unbreakable mathematical chain of custody:

$$H_0 = \text{SHA256}(\text{Genesis Block})$$
$$H_i = \text{SHA256}(i \parallel H_{i-1} \parallel t \parallel \text{target\_id} \parallel \text{event\_type} \parallel \text{evidence\_hash} \parallel \text{metadata})$$

If an adversary alters even a single character in an archived evidence JSON document or modifies a risk score in the database, the live verification check:
$$\text{Recalculated } H \neq \text{Anchored } H$$
immediately triggers an `INTEGRITY_FAILURE` alert and flags the case as compromised.

---

## 4. Model Lifecycle & Isolation

- **In-Memory Singletons:** Deep neural network models (SCRFD Face Detector, ArcFace Embedding Engine, MiniFASNet PAD) are initialized once during FastAPI startup.
- **CPU Determinism:** Models run with deterministic threadpools and CPU fallbacks to ensure repeatable scoring across deployment platforms without relying on proprietary GPU architectures.
- **Corrupted Model Safeguards:** Missing or corrupted model weights raise explicit startup configuration exceptions rather than silently degrading into fake predictions.

---

## 5. Ledger Resilience & Non-Blocking Screening

Blockchain outages must never paralyze border control operations:
- If disk persistence fails or the ledger becomes temporarily unavailable, the `AuditIntegrityService` queues the event in an in-memory `_pending_queue`.
- The verification pipeline completes uninterrupted.
- Queued events are retried automatically when the ledger recovers.
