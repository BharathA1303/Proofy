/**
 * verificationApi.js
 *
 * Frontend API abstraction layer for the verification backend (FastAPI).
 *
 * Phase 0: All functions are STUBS.
 * They throw "Verification service unavailable" to make it explicit
 * that no real backend exists yet. Do NOT fake successful responses.
 *
 * Phase 1 integration steps:
 *   1. Set VITE_API_BASE_URL in .env.local
 *   2. Implement each function body using the axios instance below
 *   3. Map FastAPI response shapes to the frontend session state
 *   4. Call actions.setTraveler(), actions.setChecks() etc. from
 *      the component or a custom hook that consumes these functions
 *
 * IMPORTANT: All user-facing error messages must be filtered here.
 * Raw exceptions must NEVER reach the UI as-is.
 * Use formatError() to produce safe, readable messages.
 */

import axios from 'axios';
import { API_BASE_URL } from '../config/appConfig.js';

/* ------------------------------------------------------------------ */
/*  Axios instance                                                       */
/* ------------------------------------------------------------------ */

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120_000,
  headers: {
    Accept: 'application/json',
  },
});

/* ------------------------------------------------------------------ */
/*  Error formatter — keeps raw details out of the UI                   */
/* ------------------------------------------------------------------ */

/**
 * Maps any caught error to a user-facing string.
 * Logs the raw error to the console for debugging.
 *
 * @param {unknown} err
 * @param {string}  fallbackMessage
 * @returns {string}
 */
function formatError(err, fallbackMessage = 'An unexpected error occurred. Please try again.') {
  if (process.env.NODE_ENV !== 'production') {
    console.error('[verificationApi]', err);
  }

  if (axios.isAxiosError(err)) {
    if (!err.response) {
      return 'Verification service unavailable. Please check your connection and try again.';
    }
    const backendDetail = err.response.data?.detail;
    if (typeof backendDetail === 'string' && backendDetail.trim()) {
      return backendDetail.trim();
    }
    switch (err.response.status) {
      case 400: return 'Invalid document submission. Please check your file and try again.';
      case 401: return 'Authentication required. Please log in and try again.';
      case 403: return 'You do not have permission to perform this verification.';
      case 404: return 'Verification session not found. Please start a new verification.';
      case 413: return 'Document file is too large. Please reduce the file size and try again.';
      case 415: return 'Unsupported document format. Please upload a JPEG, PNG, or PDF file.';
      case 429: return 'Too many requests. Please wait a moment and try again.';
      case 500:
      case 502:
      case 503:
      case 504: return 'Verification service unavailable. Please try again shortly.';
      default:  return fallbackMessage;
    }
  }

  return fallbackMessage;
}

/* ------------------------------------------------------------------ */
/*  Phase 0 stub marker                                                  */
/* ------------------------------------------------------------------ */

/**
 * Throws a clear stub error. Replaced with real implementation in Phase 1.
 */
function stubNotImplemented(fnName) {
  throw new Error(
    `[Phase 0 Stub] ${fnName} is not yet connected to the backend. ` +
    'Set FEATURES.BACKEND_ENABLED = true and implement the function body.'
  );
}

/* ------------------------------------------------------------------ */
/*  API surface                                                          */
/* ------------------------------------------------------------------ */

/**
 * Pre-flight optical quality gate check (Gate 1).
 * Calls POST /api/v1/verification/quality-check (< 20ms).
 *
 * @param {File} file
 * @param {string} documentType
 * @returns {Promise<DocumentQualityResponse>}
 */
export async function checkDocumentQuality(file, documentType = 'passport') {
  const form = new FormData();
  form.append('file', file);
  form.append('document_type', documentType);

  try {
    const { data } = await apiClient.post('/api/v1/verification/quality-check', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  } catch (err) {
    throw new Error(formatError(err, 'Failed to evaluate document quality.'));
  }
}

/**
 * Run OCR extraction on a document image.
 *
 * Phase 1: POST /api/v1/verification/ocr
 *
 * Sends the image as multipart/form-data and returns the structured
 * OCR result including traveler fields and MRZ data.
 *
 * @param {File}   file           — the document File object
 * @param {string} documentType   — one of DOCUMENT_TYPES values (e.g. 'passport')
 * @returns {Promise<PassportOCRResponse>}
 *
 * PassportOCRResponse shape:
 * {
 *   verification_id: string,
 *   document_type:   string,
 *   status:          'completed' | 'partial' | 'failed',
 *   traveler: {
 *     name, docNumber, dob, nationality, gender,
 *     placeOfBirth, authority, issuedDate, expiry, mrz
 *   },
 *   mrz: { line1, line2, raw_line1, raw_line2, confidence_line1, confidence_line2 },
 *   ocr: { overall_confidence, region_count, has_low_confidence_regions }
 * }
 */
export async function uploadDocument(file, documentType) {
  const form = new FormData();
  form.append('file', file);
  form.append('document_type', documentType);

  try {
    const { data } = await apiClient.post('/api/v1/verification/ocr', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  } catch (err) {
    throw new Error(formatError(err, 'Failed to process document. Please try again.'));
  }
}

/**
 * Validate extracted document data (Module 2).
 *
 * Calls POST /api/v1/verification/validate with structured OCR and traveler data.
 * Returns ICAO checksums, structural checks, and VIZ-MRZ cross-check findings.
 *
 * @param {string} verificationId
 * @param {string} documentType
 * @param {object|null} mrzData
 * @param {object|null} travelerFields
 * @returns {Promise<object>} PassportValidationResponse
 */
export async function validateDocument(verificationId, documentType, mrzData, travelerFields) {
  try {
    const payload = {
      verification_id: verificationId,
      document_type: documentType,
      mrz: mrzData ?? null,
      traveler: travelerFields ?? null,
    };
    const { data } = await apiClient.post('/api/v1/verification/validate', payload);
    return data;
  } catch (err) {
    throw new Error(formatError(err, 'Failed to validate document. Please try again.'));
  }
}

/**
 * Poll the current pipeline status for a verification session.
 *
 * Phase 1: GET /api/v1/verify/{sessionId}/status
 *
 * @param {string} sessionId
 * @returns {Promise<{ status: string, stage: string }>}
 */
export async function getVerificationStatus(sessionId) {
  void sessionId;
  stubNotImplemented('getVerificationStatus');

  // Phase 1:
  // try {
  //   const { data } = await apiClient.get(`/api/v1/verify/${sessionId}/status`);
  //   return { status: data.status, stage: data.stage };
  // } catch (err) {
  //   throw new Error(formatError(err, 'Failed to fetch verification status.'));
  // }
}

/**
 * Fetch the final verification result once the pipeline completes.
 *
 * Phase 1: GET /api/v1/verify/{sessionId}/result
 *
 * @param {string} sessionId
 * @returns {Promise<VerificationResult>}
 */
export async function getVerificationResult(sessionId) {
  void sessionId;
  stubNotImplemented('getVerificationResult');

  // Phase 1:
  // try {
  //   const { data } = await apiClient.get(`/api/v1/verify/${sessionId}/result`);
  //   return data;
  // } catch (err) {
  //   throw new Error(formatError(err, 'Failed to fetch verification result.'));
  // }
}

/**
 * Run tampering & forensic analysis on the ORIGINAL document image (Module 3).
 *
 * Calls POST /api/v1/verification/forensic with the same original File object
 * that was submitted to /ocr — Module 3 must operate on the original upload,
 * not any OCR-preprocessed copy, so the raw file is resent rather than any
 * derived image.
 *
 * @param {File}   file           — the ORIGINAL document File object
 * @param {string} documentType   — current document type key (e.g. 'passport')
 * @param {string} verificationId — verification_id returned by uploadDocument()
 * @returns {Promise<object>} ForensicAnalysisResponse
 */
export async function runForensicAnalysis(file, documentType, verificationId) {
  const form = new FormData();
  form.append('file', file);
  form.append('document_type', documentType);
  form.append('verification_id', verificationId);

  try {
    const { data } = await apiClient.post('/api/v1/verification/forensic', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  } catch (err) {
    throw new Error(formatError(err, 'Failed to run forensic analysis. Please try again.'));
  }
}

/**
 * Fetch detailed forensic evidence for a completed session.
 *
 * Phase 1: GET /api/v1/verify/{sessionId}/forensic
 *
 * @param {string} sessionId
 * @returns {Promise<ForensicEvidenceItem[]>}
 */
export async function getForensicEvidence(sessionId) {
  void sessionId;
  stubNotImplemented('getForensicEvidence');

  // Phase 1:
  // try {
  //   const { data } = await apiClient.get(`/api/v1/verify/${sessionId}/forensic`);
  //   return data.evidence ?? [];
  // } catch (err) {
  //   throw new Error(formatError(err, 'Failed to fetch forensic evidence.'));
  // }
}

/**
 * Run biometric face verification and presentation attack detection (Module 4).
 *
 * Calls POST /api/v1/verification/face with:
 *   - verification_id
 *   - document_type
 *   - live_frame (Blob/File)
 *   - optional sequence frames
 *   - optional document_image fallback
 *
 * @param {string} verificationId
 * @param {string} documentType
 * @param {Blob|File} liveFrame
 * @param {Array<Blob|File>|null} sequenceFrames
 * @param {File|null} documentImageFallback
 * @returns {Promise<object>} FaceVerificationResponse
 */
export async function verifyBiometrics(
  verificationId,
  documentType,
  liveFrame,
  sequenceFrames = null,
  documentImageFallback = null
) {
  const form = new FormData();
  form.append('verification_id', verificationId);
  form.append('document_type', documentType);
  form.append('live_frame', liveFrame, 'live_frame.jpg');

  if (sequenceFrames && sequenceFrames.length > 0) {
    sequenceFrames.forEach((frame, idx) => {
      form.append('live_frames', frame, `seq_${idx}.jpg`);
    });
  }

  if (documentImageFallback) {
    form.append('document_image', documentImageFallback);
  }

  try {
    const { data } = await apiClient.post('/api/v1/verification/face', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  } catch (err) {
    throw new Error(formatError(err, 'Failed to complete face verification. Please try again.'));
  }
}

/**
 * Cancel an in-progress verification session.
 *
 * Phase 1: DELETE /api/v1/verify/{sessionId}
 *
 * @param {string} sessionId
 * @returns {Promise<void>}
 */
export async function cancelVerification(sessionId) {
  void sessionId;
  stubNotImplemented('cancelVerification');
}


/**
 * Run registry verification (Module 5).
 *
 * Calls POST /api/v1/verification/registry with verification_id and document_type.
 *
 * SECURITY: The client NEVER re-submits identity fields.
 * The server retrieves normalized session data from its internal registry session store
 * (populated during /ocr). Only the session reference is needed here.
 *
 * DEVELOPMENT MODE: Uses a clearly-labeled development mock registry.
 * The response always contains source_type='development_mock' in provider_metadata.
 * Never present this as "Government Verified" in the UI.
 *
 * Response shape (RegistryVerificationResponse):
 * {
 *   verification_id: string,
 *   document_type:   string,
 *   registry: {
 *     provider: string,
 *     status:  'MATCHED'|'NOT_FOUND'|'MISMATCH'|'REVOKED'|'EXPIRED'|'SUSPENDED'|
 *              'UNAVAILABLE'|'TIMEOUT'|'PROVIDER_ERROR'|'AUTHENTICATION_ERROR'|'INCONCLUSIVE',
 *     record_found: boolean,
 *     registry_document_status: string|null
 *   },
 *   field_results: Array<{
 *     field: string,
 *     document_value: string|null,
 *     registry_value: string|null,
 *     status: 'MATCH'|'MISMATCH'|'MISSING_IN_REGISTRY'|'MISSING_IN_DOCUMENT'|'NOT_COMPARED',
 *     is_critical: boolean,
 *     note: string|null
 *   }>,
 *   evidence: Array<{ type, severity, description }>,
 *   provider_metadata: {
 *     provider_id: string,
 *     source_type: 'development_mock'|'sandbox'|'authorized_external',
 *     response_time_ms: number
 *   },
 *   audit: object
 * }
 *
 * @param {string} verificationId  — session ID from Module 1 /ocr
 * @param {string} documentType    — e.g. 'passport'
 * @returns {Promise<object>} RegistryVerificationResponse
 */
export async function runRegistryVerification(verificationId, documentType) {
  try {
    const { data } = await apiClient.post('/api/v1/verification/registry', {
      verification_id: verificationId,
      document_type: documentType,
    });
    return data;
  } catch (err) {
    throw new Error(
      formatError(err, 'Registry verification could not be completed. Please try again.')
    );
  }
}



/**
 * Run Module 6 risk assessment.
 *
 * Calls POST /api/v1/verification/risk with verification_id and document_type.
 *
 * SECURITY: The client NEVER submits risk_score, risk_level, reasons, or any
 * evidence field. All evidence is read server-side from the risk session store
 * populated by the preceding M1–M5 endpoints.
 *
 * IMPORTANT: The officer_recommendation is ADVISORY ONLY.
 * Never label it as "Decision", "Verdict", or "Outcome" in the UI.
 * Never display "admitted", "denied", "forged", "authentic", or related vocabulary.
 *
 * Response shape (RiskAssessmentResponse):
 * {
 *   verification_id: string,
 *   document_type:   string,
 *   risk_assessment: {
 *     risk_score:             number (0–100, NOT a fraud probability),
 *     risk_level:             'LOW'|'MEDIUM'|'HIGH'|'CRITICAL',
 *     officer_recommendation: string (advisory only),
 *     risk_config_version:    string,
 *     reasons:   Array<RiskReasonDetail>,
 *     category_breakdown: Array<CategoryContributionDetail>,
 *     module_summary:     Array<ModuleSummaryItem>,
 *     completeness:       number (0.0–1.0),
 *     uncertainties:      Array<UncertaintyItem>,
 *     conflict_detected:  boolean,
 *     conflicts:          Array<ConflictDetail>,
 *     evidence_count:     number,
 *   }
 * }
 *
 * @param {string} verificationId — session ID from Module 1 /ocr
 * @param {string} documentType   — e.g. 'passport'
 * @returns {Promise<object>} RiskAssessmentResponse
 */
export async function runRiskAssessment(verificationId, documentType) {
  try {
    const { data } = await apiClient.post('/api/v1/verification/risk', {
      verification_id: verificationId,
      document_type:   documentType,
    });
    return data;
  } catch (err) {
    throw new Error(
      formatError(err, 'Risk assessment could not be completed. Please try again.')
    );
  }
}


/* ------------------------------------------------------------------ */
/*  Named export for the configured client (useful in Phase 1 hooks)    */
/* ------------------------------------------------------------------ */
export { apiClient, formatError };
