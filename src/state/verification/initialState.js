/**
 * initialState.js
 *
 * The single source of truth for a clean, empty verification session.
 *
 * IMPORTANT: All values must represent "nothing has been submitted yet."
 * No hardcoded traveler data.
 * No hardcoded verification results.
 * No fake scores.
 *
 * This object is also used to RESET state when the user switches
 * document types — see verificationReducer.js SELECT_DOCUMENT_TYPE.
 */

import { DOCUMENT_TYPES } from '../../config/documentProfiles.js';

/**
 * Verification session status values.
 * Used as a lightweight state machine — ready for future async pipeline.
 *
 * Phase 0 active states:
 *   standby          → Nothing loaded. Application opens here.
 *   document_selected→ User chose a real file (Choose File / Drag & Drop).
 *   sample_selected  → User explicitly clicked "Load Sample" button.
 *
 * Phase 1+ states (pipeline progression):
 *   uploading        → File being transmitted to backend.
 *   processing       → Backend pipeline running (covers all AI/ML modules).
 *   completed        → Full pipeline finished successfully.
 *   error            → An error occurred at any stage.
 *
 * Phase 0 flow:
 *   standby → document_selected
 *   standby → sample_selected
 *
 * Phase 1+ flow:
 *   document_selected → uploading → processing → completed
 *                                              → error
 */
export const SESSION_STATUS = {
  STANDBY:           'standby',
  DOCUMENT_SELECTED: 'document_selected',
  SAMPLE_SELECTED:   'sample_selected',
  UPLOADING:         'uploading',
  PROCESSING:        'processing',
  COMPLETED:         'completed',
  ERROR:             'error',
};

/** Verification check result values */
export const CHECK_STATUS = {
  PENDING: 'pending',
  READY:   'ready',
  PASSED:  'passed',
  FAILED:  'failed',
  WARNING: 'warning',
  SKIPPED: 'skipped',
};


/**
 * Decision values for the top-level result object.
 *
 * These are values of result.decision — NOT the result itself.
 * result is always an object (or null), never a bare string.
 *
 * Future result object shape (Phase 1):
 * {
 *   decision: DECISION.CLEARED | DECISION.REVIEW | DECISION.REJECTED,
 *   // more fields added by backend response mapping
 * }
 *
 * Kept separate from risk so the backend can evolve each independently:
 *   result.decision  — overall officer-facing verdict
 *   risk.score       — numeric threat index 0–100
 *   risk.level       — low | medium | high | critical
 *   risk.reasons     — string[] explaining the score
 */
export const DECISION = {
  CLEARED:  'cleared',
  REVIEW:   'review',
  REJECTED: 'rejected',
};

/**
 * Returns a fresh, empty verification session.
 * Call this when creating the initial state or when resetting.
 *
 * @param {string} documentType — one of DOCUMENT_TYPES values
 */
export function createInitialSession(documentType = DOCUMENT_TYPES.PASSPORT) {
  return {
    documentType,

    status: SESSION_STATUS.STANDBY,

    /** Active workflow stage (1: Intake & Selection, 2: Officer Inspection, 3: Live Face Match, 4: Final Clearance) */
    workflowStage: 1,
    maxUnlockedStage: 1,
    isMockVector: false,
    capturedLiveImage: null,
    documentFaceImage: null,
    verificationDuration: null,
    documentQuality: null,

    /** Active pipeline milestone: 0 = standby, 1 = extraction, 2 = validation, 3 = forensics, 4 = biometrics, 5 = registryRisk */
    activeMilestone: 0,
    milestones: {
      extraction:   { id: 1, label: 'OCR & Intake',        status: 'idle', desc: 'Text & MRZ extraction' },
      validation:   { id: 2, label: 'Format Validation',    status: 'idle', desc: 'Rules & check digits' },
      forensics:    { id: 3, label: 'Forensic Tampering',   status: 'idle', desc: 'ELA & splicing scan' },
      biometrics:   { id: 4, label: 'Facial Biometrics',   status: 'idle', desc: 'Liveness & face gate' },
      registryRisk: { id: 5, label: 'Decision & Registry', status: 'idle', desc: 'Risk matrix & ledger' },
    },

    /** The File object selected by the user. null = nothing selected. */
    file: null,

    /** Human-readable filename for display purposes */
    fileName: null,

    /** Whether the file came from the sample library (not a real upload) */
    isSample: false,

    /** Traveler information extracted from the document */
    traveler: {
      name:         '',
      docNumber:    '',
      dob:          '',
      nationality:  '',
      authority:    '',
      expiry:       '',
      issuedDate:   '',
      gender:       '',
      placeOfBirth: '',
      mrz:          '',
      vehicleClass: '',
      permitType:   '',
      portOfEntry:  '',
      visaType:     '',
      visaCategory: '',
    },

    /** Biometric analysis results (Module 4) */
    biometrics: {
      faceMatch: null,   // percentage number 0–100 or null (neutral '--%')
      liveness:  null,   // percentage number 0–100 or null (neutral '--%')
      status:    'pending', // 'pending' | 'ready' | 'capturing' | 'processing' | 'completed' | 'failed' | 'model_unavailable'
      documentFace: {
        detected: false,
        status: 'pending',
        quality: null,
        details: null,
        error: null,
      },
      liveFace: {
        detected: false,
        status: 'pending',
        quality: null,
        details: null,
        error: null,
      },
      antiSpoof: {
        status: 'pending', // 'pending' | 'pass' | 'suspected_spoof' | 'inconclusive' | 'model_unavailable'
        score: null,
        explanation: '',
      },
      faceMatchResult: {
        status: 'pending', // 'pending' | 'match' | 'no_match' | 'inconclusive' | 'unavailable'
        similarity: null,
        threshold: 0.40,
        explanation: '',
      },
      secondaryPad: null,
      overallAssessment: null,
      summary: '',
    },

    /** Individual check results */
    checks: {
      documentValidation:   CHECK_STATUS.PENDING,
      tamperingDetection:   CHECK_STATUS.PENDING,
      faceVerification:     CHECK_STATUS.PENDING,
      registryVerification: CHECK_STATUS.PENDING,
      riskAssessment:       CHECK_STATUS.PENDING,
    },

    /** Module 2 validation details and checksum evidence. null = not validated yet. */
    validationDetail: null,

    /** Module 3 forensic analysis summary (overall_assessment, signals, photo_region). null = not analyzed yet. */
    forensicDetail: null,

    /** Module 4 biometric face verification response. null = not evaluated yet. */
    faceDetail: null,

    /** Module 5 registry verification response. null = not evaluated yet. */
    registryDetail: null,


    /**
     * Top-level verification result.
     * null  → no result yet (standby, processing)
     * object → { decision: DECISION.*, ... } populated by backend response
     *
     * Do NOT set this to a bare string like 'cleared'.
     * Always use: actions.setResult({ decision: DECISION.CLEARED })
     */
    result: null,

    /** Forensic evidence items returned by the backend */
    forensicEvidence: [],

    /**
     * Module 6: Risk Assessment.
     *
     * Populated by runRiskAssessment() → the full RiskAssessmentResponse.
     * null = not yet run.
     *
     * Shape when populated:
     *   risk.data = {
     *     risk_score:             number (0–100),
     *     risk_level:             'LOW'|'MEDIUM'|'HIGH'|'CRITICAL',
     *     officer_recommendation: string (ADVISORY ONLY),
     *     risk_config_version:    string,
     *     reasons:                RiskReasonDetail[],
     *     category_breakdown:     CategoryContributionDetail[],
     *     module_summary:         ModuleSummaryItem[],
     *     completeness:           number (0.0–1.0),
     *     uncertainties:          UncertaintyItem[],
     *     conflict_detected:      boolean,
     *     conflicts:              ConflictDetail[],
     *     evidence_count:         number,
     *   }
     *
     * NEVER: store admission/denial/verdict status here.
     * NEVER: client-set risk_score or level. Always populated by backend.
     */
    risk: {
      loading: false,     // true while waiting for /risk response
      error:   null,      // user-facing error string or null
      data:    null,      // full risk_assessment dict from backend or null
    },

    /** User-facing error message. null = no error. */
    error: null,

    /** Backend session/job ID assigned after upload */
    sessionId: null,
  };
}

/** The application's initial state */
export const initialState = createInitialSession(DOCUMENT_TYPES.PASSPORT);
