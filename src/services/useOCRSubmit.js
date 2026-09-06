/**
 * useOCRSubmit.js
 *
 * Custom hook: orchestrates the frontend OCR submission flow.
 *
 * Responsibilities:
 *   1. Validates that a file is available to submit
 *   2. Transitions state machine: → UPLOADING → PROCESSING → COMPLETED / ERROR
 *   3. Calls verificationApi.uploadDocument()
 *   4. Maps the backend response to the verification context
 *   5. Surfaces safe user-facing error messages
 *
 * This hook is consumed by UploadPanel's "Verify Document" button.
 * It does NOT handle file selection — that's handled separately by the
 * UploadPanel drag-and-drop / file input handlers.
 *
 * Phase 1: Only Passport OCR is wired.
 * For other document types, the hook shows a clear "not yet implemented" message.
 */

import { useCallback, useState } from 'react';
import { runForensicAnalysis, uploadDocument, validateDocument } from './verificationApi.js';
import { useVerification } from '../state/verification/useVerification.js';
import { SESSION_STATUS } from '../state/verification/initialState.js';
import { DOCUMENT_PROFILES } from '../config/documentProfiles.js';
import { FEATURES } from '../config/appConfig.js';

const SIGNAL_LABELS = {
  ela: 'Error Level Analysis',
  photo_boundary: 'Photo Boundary',
  compression: 'Compression Analysis',
  metadata: 'Metadata',
};

/**
 * Maps a Module 3 signal (status + severity) to the evidence panel's
 * severity vocabulary ('info' | 'warning' | 'critical').
 * Note: this is a DISPLAY mapping only — it never feeds back into any
 * scoring or decision logic.
 */
function mapSignalSeverity(status, severity) {
  if (status === 'unavailable' || status === 'insufficient_data') return 'info';
  if (status !== 'suspicious') return 'info';
  return severity === 'high' ? 'critical' : 'warning';
}

/**
 * Maps the Module 3 overall_assessment to a Tampering Detection check status.
 */
function mapTamperingCheckStatus(overallAssessment) {
  switch (overallAssessment) {
    case 'no_significant_anomaly': return 'passed';
    case 'suspicious': return 'warning';
    case 'high_forensic_concern': return 'failed';
    default: return 'warning'; // insufficient_data
  }
}

/**
 * @returns {{ submitOCR: function, isSubmitting: boolean }}
 */
export function useOCRSubmit() {
  const { actions } = useVerification();
  const [isSubmitting, setIsSubmitting] = useState(false);

  /**
   * Trigger the OCR submission pipeline.
   *
   * @param {File} file            — the File object to submit
   * @param {string} documentType  — current document type key
   */
  const submitOCR = useCallback(async (file, documentType) => {
    // Guard: backend must be enabled
    if (!FEATURES.BACKEND_ENABLED) {
      actions.setError('Verification service is not yet enabled. Please check configuration.');
      return;
    }

    // Guard: only process documents whose profile status is available
    const profile = DOCUMENT_PROFILES[documentType];
    if (!profile || profile.status !== 'available') {
      actions.setError(
        `Verification for ${profile?.label || documentType} is not yet supported. ` +
        'Passport, Visa, Driving License, National ID, and Border Permit verification are operational.'
      );
      return;
    }

    // Guard: must have a file
    if (!file) {
      actions.setError('No document selected. Please choose a file to verify.');
      return;
    }

    // Guard: prevent double-submission
    if (isSubmitting) return;

    // Clear any existing errors before starting
    actions.clearError();
    setIsSubmitting(true);

    try {
      // ── Phase 1a: UPLOADING ───────────────────────────────────────────
      actions.setStatus(SESSION_STATUS.UPLOADING);

      const ocrResult = await uploadDocument(file, documentType);

      // ── Phase 1b: PROCESSING (brief state for UI feedback) ────────────
      actions.setStatus(SESSION_STATUS.PROCESSING);

      // Store backend session ID
      if (ocrResult.verification_id) {
        actions.setSessionId(ocrResult.verification_id);
      }

      // Map backend traveler fields to the context state.
      // Backend returns camelCase keys that match the context exactly.
      // Any null/undefined fields are left as empty strings (initialState default).
      const travelerPayload = {};
      const backendTraveler = ocrResult.traveler ?? {};

      const fieldMap = [
        'name', 'docNumber', 'dob', 'nationality',
        'gender', 'placeOfBirth', 'authority', 'issuedDate', 'expiry', 'mrz',
        'passportNumber', 'visaType', 'entries', 'durationOfStay',
        'licenseNumber', 'vehicleClass', 'bloodGroup', 'validFrom', 'validTo', 'state',
        'identityNumber', 'maskedIdentityNumber', 'yearOfBirth', 'address', 'qrPayload',
        'permitNumber', 'permitType', 'borderZone', 'portOfEntry',
      ];

      for (const key of fieldMap) {
        if (backendTraveler[key] != null) {
          travelerPayload[key] = backendTraveler[key];
        }
      }

      if (Object.keys(travelerPayload).length > 0) {
        actions.setTraveler(travelerPayload);
      }

      // ── Phase 2: MODULE 2 — DOCUMENT VALIDATION ──────────────────────
      let validationDetail = null;
      let validationStatus = 'warning';

      try {
        const valResponse = await validateDocument(
          ocrResult.verification_id,
          documentType,
          ocrResult.mrz,
          ocrResult.traveler
        );
        if (valResponse?.document_validation) {
          validationDetail = valResponse.document_validation;
          const rawStatus = validationDetail.status;
          if (rawStatus === 'passed') {
            validationStatus = 'passed';
          } else if (rawStatus === 'failed') {
            validationStatus = 'failed';
          } else {
            validationStatus = 'warning';
          }
        }
      } catch (valErr) {
        console.warn('Module 2 validation error:', valErr);
        validationStatus = 'warning';
      }

      // Store validation evidence in context
      if (validationDetail) {
        actions.setValidationDetail(validationDetail);
      }

      // Update checks: documentValidation from Module 2.
      // tamperingDetection is set below once Module 3 completes (or falls
      // back to 'warning' if forensic analysis could not run).
      actions.setChecks({
        documentValidation: validationStatus,
      });

      // ── Phase 3: MODULE 3 — TAMPERING & FORENSIC ANALYSIS ────────────
      // Operates on the ORIGINAL uploaded file (not any OCR-preprocessed
      // copy), so we resend the same File object submitted to /ocr.
      let forensicSummary = null;
      let tamperingStatus = 'warning';

      try {
        const forensicResponse = await runForensicAnalysis(
          file,
          documentType,
          ocrResult.verification_id
        );
        forensicSummary = forensicResponse?.forensic_analysis ?? null;
        if (forensicSummary) {
          tamperingStatus = mapTamperingCheckStatus(forensicSummary.overall_assessment);
        }
      } catch (forErr) {
        console.warn('Module 3 forensic analysis error:', forErr);
        tamperingStatus = 'warning';
      }

      actions.setForensicDetail(forensicSummary);

      const evidenceItems = (forensicSummary?.signals ?? []).map((signal) => ({
        id: signal.type,
        type: signal.type,
        label: SIGNAL_LABELS[signal.type] ?? signal.type,
        severity: mapSignalSeverity(signal.status, signal.severity),
        detail: signal.description,
      }));
      actions.setForensicEvidence(evidenceItems);

      actions.setChecks({
        tamperingDetection: tamperingStatus,
        faceVerification: 'ready',
      });

      actions.setBiometrics({
        status: 'ready',
      });

      // ── Final Status & Result (Neutral, never CLEARED) ────────────────
      const ocrStatus = ocrResult.status ?? 'partial';
      actions.setResult({
        decision: 'review',         // Module 2/3 evidence ≠ clearance
        ocrStatus,
        validationStatus,
        tamperingStatus,
        overallConfidence: ocrResult.ocr?.overall_confidence ?? null,
        regionCount: ocrResult.ocr?.region_count ?? 0,
        hasLowConfidence: ocrResult.ocr?.has_low_confidence_regions ?? false,
        note: 'Phase 4: OCR extraction, document validation, and forensic analysis complete. Face verification is ready for manual operator initiation. Registry lookup and risk assessment remain pending.',
      });


    } catch (err) {
      // err.message is already sanitised by formatError() in verificationApi.js
      actions.setError(err.message || 'Verification failed. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  }, [actions, isSubmitting]);

  return { submitOCR, isSubmitting };
}
