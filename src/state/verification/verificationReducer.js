/**
 * verificationReducer.js
 *
 * Pure reducer for the verification session state machine.
 * All state transitions happen here — nowhere else.
 *
 * Actions:
 *   SELECT_DOCUMENT_TYPE  Switch tab — always resets the full session
 *   SELECT_FILE           User chose a real file
 *   SELECT_SAMPLE         User explicitly clicked "Load Sample"
 *   CLEAR_FILE            User removed the selected file
 *   SET_STATUS            Update pipeline status (for future async pipeline)
 *   SET_TRAVELER          Populate traveler fields (from OCR response)
 *   SET_BIOMETRICS        Populate biometric results
 *   SET_CHECKS            Update one or all check results
 *   SET_RESULT            Set the top-level verification result
 *   SET_FORENSIC_EVIDENCE Set forensic evidence array
 *   SET_RISK              Set risk score/level/reasons
 *   SET_SESSION_ID        Store backend-assigned session ID
 *   SET_ERROR             Store a user-friendly error message
 *   CLEAR_ERROR           Remove error state
 *   RESET_SESSION         Full reset to standby (keeps documentType)
 */

import { createInitialSession, SESSION_STATUS } from './initialState.js';

export const ACTIONS = {
  SELECT_DOCUMENT_TYPE:  'SELECT_DOCUMENT_TYPE',
  SELECT_FILE:           'SELECT_FILE',
  SELECT_SAMPLE:         'SELECT_SAMPLE',
  CLEAR_FILE:            'CLEAR_FILE',
  SET_STATUS:            'SET_STATUS',
  SET_TRAVELER:          'SET_TRAVELER',
  SET_BIOMETRICS:        'SET_BIOMETRICS',
  SET_CHECKS:            'SET_CHECKS',
  SET_VALIDATION_DETAIL: 'SET_VALIDATION_DETAIL',
  SET_FORENSIC_DETAIL:   'SET_FORENSIC_DETAIL',
  SET_FACE_DETAIL:       'SET_FACE_DETAIL',
  SET_REGISTRY_DETAIL:   'SET_REGISTRY_DETAIL',
  RESET_BIOMETRICS:      'RESET_BIOMETRICS',
  SET_RESULT:            'SET_RESULT',

  SET_FORENSIC_EVIDENCE: 'SET_FORENSIC_EVIDENCE',
  SET_RISK:              'SET_RISK',
  SET_SESSION_ID:        'SET_SESSION_ID',
  SET_ERROR:             'SET_ERROR',
  CLEAR_ERROR:           'CLEAR_ERROR',
  RESET_SESSION:         'RESET_SESSION',
};

/**
 * @param {object} state  — current verification session
 * @param {{ type: string, payload: any }} action
 * @returns {object}  — next state (new reference)
 */
export function verificationReducer(state, action) {
  switch (action.type) {

    /**
     * SELECT_DOCUMENT_TYPE
     * Switches the active document type and resets the entire session.
     * This enforces the rule: no information leaks between tabs.
     *
     * payload: string — new document type key
     */
    case ACTIONS.SELECT_DOCUMENT_TYPE:
      return createInitialSession(action.payload);

    /**
     * SELECT_FILE
     * User selected a real file through Choose File or Drag & Drop.
     * Only updates state — does NOT trigger any processing.
     *
     * payload: { file: File, fileName: string }
     */
    case ACTIONS.SELECT_FILE:
      return {
        ...state,
        file:     action.payload.file,
        fileName: action.payload.fileName,
        isSample: false,
        status:   SESSION_STATUS.DOCUMENT_SELECTED,
        error:    null,
      };

    /**
     * SELECT_SAMPLE
     * User explicitly clicked "Load Sample" button.
     * Marks session as sample_selected but does NOT auto-run anything.
     *
     * payload: { fileName: string, sampleKey: string }
     */
    case ACTIONS.SELECT_SAMPLE:
      return {
        ...state,
        file:      null,
        fileName:  action.payload.fileName,
        isSample:  true,
        status:    SESSION_STATUS.SAMPLE_SELECTED,
        error:     null,
      };

    /**
     * CLEAR_FILE
     * User removed the selected file — return to standby.
     * Keeps the current documentType.
     */
    case ACTIONS.CLEAR_FILE:
      return createInitialSession(state.documentType);

    /**
     * SET_STATUS
     * Updates pipeline progress status.
     *
     * payload: string — one of SESSION_STATUS values
     */
    case ACTIONS.SET_STATUS:
      return { ...state, status: action.payload };

    /**
     * SET_TRAVELER
     * Merges partial or complete traveler field data.
     * Typically called when OCR results arrive from backend.
     *
     * payload: Partial<traveler>
     */
    case ACTIONS.SET_TRAVELER:
      return {
        ...state,
        traveler: { ...state.traveler, ...action.payload },
      };

    /**
     * SET_BIOMETRICS
     * Merges biometric results.
     *
     * payload: { faceMatch?: number, liveness?: number }
     */
    case ACTIONS.SET_BIOMETRICS:
      return {
        ...state,
        biometrics: { ...state.biometrics, ...action.payload },
      };

    /**
     * SET_CHECKS
     * Merges one or more check result updates.
     *
     * payload: Partial<checks> e.g. { tamperingDetection: 'passed' }
     */
    case ACTIONS.SET_CHECKS:
      return {
        ...state,
        checks: { ...state.checks, ...action.payload },
      };

    /**
     * SET_VALIDATION_DETAIL
     * Stores the Module 2 validation evidence and checksum breakdown.
     *
     * payload: object — DocumentValidationSummary or null
     */
    case ACTIONS.SET_VALIDATION_DETAIL:
      return {
        ...state,
        validationDetail: action.payload,
      };

    /**
     * SET_FORENSIC_DETAIL
     * Stores the Module 3 forensic analysis summary (overall_assessment,
     * explanation, signals, photo_region).
     *
     * payload: object — ForensicAnalysisSummary or null
     */
    case ACTIONS.SET_FORENSIC_DETAIL:
      return {
        ...state,
        forensicDetail: action.payload,
      };

    /**
     * SET_FACE_DETAIL
     * Stores the Module 4 biometric face verification summary.
     *
     * payload: object — FaceVerificationResponse or null
     */
    case ACTIONS.SET_FACE_DETAIL:
      return {
        ...state,
        faceDetail: action.payload,
      };

    /**
     * SET_REGISTRY_DETAIL
     * Stores the Module 5 registry verification response.
     *
     * payload: object — RegistryVerificationResponse or null
     */
    case ACTIONS.SET_REGISTRY_DETAIL:
      return {
        ...state,
        registryDetail: action.payload,
      };

    /**
     * RESET_BIOMETRICS
     * Resets biometric telemetry back to neutral standby without losing earlier module results.
     */
    case ACTIONS.RESET_BIOMETRICS:
      return {
        ...state,
        biometrics: createInitialSession(state.documentType).biometrics,
        faceDetail: null,
      };


    /**
     * SET_RESULT
     * Sets the top-level verification result.
     *
     * payload: { decision: string, ...additionalFields }
     *   e.g. { decision: DECISION.CLEARED }
     *
     * result is ALWAYS an object, never a bare string.
     * This keeps result.decision separate from risk.score/level/reasons.
     */
    case ACTIONS.SET_RESULT:
      return {
        ...state,
        result: action.payload,
        status: SESSION_STATUS.COMPLETED,
      };

    /**
     * SET_FORENSIC_EVIDENCE
     * Replaces the forensic evidence array.
     *
     * payload: ForensicEvidenceItem[]
     */
    case ACTIONS.SET_FORENSIC_EVIDENCE:
      return { ...state, forensicEvidence: action.payload };

    /**
     * SET_RISK
     * Sets risk score, level, and reasons.
     *
     * payload: { score: number, level: string, reasons: string[] }
     */
    case ACTIONS.SET_RISK:
      return {
        ...state,
        risk: { ...state.risk, ...action.payload },
      };

    /**
     * SET_SESSION_ID
     * Stores the backend-assigned job/session ID for status polling.
     *
     * payload: string
     */
    case ACTIONS.SET_SESSION_ID:
      return { ...state, sessionId: action.payload };

    /**
     * SET_ERROR
     * Stores a user-friendly error message and sets status to error.
     *
     * payload: string — user-facing message (no stack traces)
     */
    case ACTIONS.SET_ERROR:
      return {
        ...state,
        status: SESSION_STATUS.ERROR,
        error:  action.payload,
      };

    /**
     * CLEAR_ERROR
     * Clears the error state without resetting the session.
     */
    case ACTIONS.CLEAR_ERROR:
      return { ...state, error: null };

    /**
     * RESET_SESSION
     * Full reset — keeps the current documentType.
     */
    case ACTIONS.RESET_SESSION:
      return createInitialSession(state.documentType);

    default:
      if (process.env.NODE_ENV !== 'production') {
        console.warn('[verificationReducer] Unknown action type:', action.type);
      }
      return state;
  }
}
