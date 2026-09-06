/**
 * auditApi.js
 *
 * Frontend service for Phase 12 Blockchain Audit, Evidence Integrity,
 * Officer Decision Support, and System Health/Diagnostics.
 */
import { API_BASE_URL } from '../config/appConfig.js';

/**
 * Retrieve the cryptographic audit chain of blocks for a case or verification target.
 *
 * @param {string} targetId Case ID (e.g. CASE-...) or Verification ID (e.g. VER-...)
 * @returns {Promise<Object>} AuditChainResponse
 */
export async function getAuditChain(targetId) {
  const res = await fetch(`${API_BASE_URL}/api/v1/audit/${encodeURIComponent(targetId)}/chain`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch audit chain for ${targetId} (${res.status})`);
  }
  return res.json();
}

/**
 * Verify cryptographic hash integrity of the live evidence against the anchored blocks.
 *
 * @param {string} targetId Case ID or Verification ID
 * @returns {Promise<Object>} IntegrityVerificationResponse
 */
export async function verifyIntegrity(targetId) {
  const res = await fetch(`${API_BASE_URL}/api/v1/audit/${encodeURIComponent(targetId)}/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to verify integrity for ${targetId} (${res.status})`);
  }
  return res.json();
}

/**
 * Record an authoritative human officer decision to the cryptographic ledger.
 *
 * @param {string} targetId Case ID or Verification ID
 * @param {Object} decisionData { officer_id, decision, reason, notes }
 * @returns {Promise<Object>} OfficerDecisionResponse
 */
export async function recordOfficerDecision(targetId, decisionData) {
  const res = await fetch(`${API_BASE_URL}/api/v1/audit/${encodeURIComponent(targetId)}/officer-decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(decisionData),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to record officer decision for ${targetId} (${res.status})`);
  }
  return res.json();
}

/**
 * Retrieve system diagnostics including model statuses and versions.
 *
 * @returns {Promise<Object>}
 */
export async function getSystemDiagnostics() {
  const res = await fetch(`${API_BASE_URL}/api/v1/system/diagnostics`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch system diagnostics (${res.status})`);
  }
  return res.json();
}

/**
 * Retrieve measured processing latency benchmarks.
 *
 * @returns {Promise<Object>}
 */
export async function getSystemBenchmarks() {
  const res = await fetch(`${API_BASE_URL}/api/v1/system/benchmarks`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch system benchmarks (${res.status})`);
  }
  return res.json();
}
