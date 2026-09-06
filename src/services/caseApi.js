/**
 * caseApi.js
 *
 * Frontend service for Phase 8 Multi-Document Verification Cases
 * and Cross-Document Intelligence.
 */
import { API_BASE_URL } from '../config/appConfig.js';

/**
 * Initialize a new verification case.
 *
 * @param {string|null} notes Optional operational notes
 * @returns {Promise<Object>} VerificationCaseResponse
 */
export async function createCase(notes = null) {
  const res = await fetch(`${API_BASE_URL}/api/v1/verification/case`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notes }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to create verification case (${res.status})`);
  }
  return res.json();
}

/**
 * Retrieve case details, active documents, relationships, and risk assessment.
 *
 * @param {string} caseId
 * @returns {Promise<Object>} VerificationCaseResponse
 */
export async function getCase(caseId) {
  const res = await fetch(`${API_BASE_URL}/api/v1/verification/case/${encodeURIComponent(caseId)}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch case ${caseId} (${res.status})`);
  }
  return res.json();
}

/**
 * Upload and attach a document to an existing case.
 *
 * @param {string} caseId
 * @param {string} documentType e.g., 'passport' | 'visa'
 * @param {File|Blob} file Image file
 * @param {boolean} replace If duplicate document type, supersede existing
 * @returns {Promise<Object>} VerificationCaseResponse
 */
export async function addDocumentToCase(caseId, documentType, file, replace = false) {
  const formData = new FormData();
  formData.append('document_type', documentType);
  formData.append('file', file);
  formData.append('replace', replace ? 'true' : 'false');

  const res = await fetch(`${API_BASE_URL}/api/v1/verification/case/${encodeURIComponent(caseId)}/documents`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to add document to case (${res.status})`);
  }
  return res.json();
}

/**
 * Remove a document from a case and invalidate dependent evidence.
 *
 * @param {string} caseId
 * @param {string} documentId e.g., 'DOC-001'
 * @returns {Promise<Object>} VerificationCaseResponse
 */
export async function removeDocumentFromCase(caseId, documentId) {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/verification/case/${encodeURIComponent(caseId)}/documents/${encodeURIComponent(documentId)}`,
    { method: 'DELETE' }
  );

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to remove document (${res.status})`);
  }
  return res.json();
}

/**
 * Trigger re-evaluation of all cross-document relationships.
 *
 * @param {string} caseId
 * @returns {Promise<Object>} VerificationCaseResponse
 */
export async function evaluateCase(caseId) {
  const res = await fetch(`${API_BASE_URL}/api/v1/verification/case/${encodeURIComponent(caseId)}/evaluate`, {
    method: 'POST',
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to evaluate relationships (${res.status})`);
  }
  return res.json();
}

/**
 * Compute or refresh case-level composite risk assessment.
 *
 * @param {string} caseId
 * @returns {Promise<Object>}
 */
export async function computeCaseRisk(caseId) {
  const res = await fetch(`${API_BASE_URL}/api/v1/verification/case/risk`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ case_id: caseId }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to compute case risk (${res.status})`);
  }
  return res.json();
}
