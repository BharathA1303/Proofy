/**
 * VerificationContext.jsx
 *
 * The single React context providing:
 *   - session        the full verification session state
 *   - dispatch       raw reducer dispatch (for complex actions)
 *   - actions        convenience action dispatchers
 *
 * Usage:
 *   const { session, actions } = useVerification();
 *   actions.selectDocumentType('visa');
 *   actions.selectFile(file);
 *
 * Wrap the application at the root:
 *   <VerificationProvider>
 *     <App />
 *   </VerificationProvider>
 */

import { useReducer, useCallback } from 'react';
import { verificationReducer, ACTIONS } from './verificationReducer.js';
import { initialState } from './initialState.js';
import { VerificationContext } from './verificationContext.js';

/**
 * Provider — place at or near root so all components share one session.
 */
export function VerificationProvider({ children }) {
  const [session, dispatch] = useReducer(verificationReducer, initialState);

  /**
   * Convenience dispatchers.
   * Components call these instead of raw dispatch — keeps action types
   * out of presentational components.
   */
  const actions = {
    /** Switch to a different document type — resets the full session */
    selectDocumentType: useCallback(
      (documentType) => dispatch({ type: ACTIONS.SELECT_DOCUMENT_TYPE, payload: documentType }),
      []
    ),

    /** User chose a real file (Choose File or Drag & Drop) */
    selectFile: useCallback(
      (file) => dispatch({
        type: ACTIONS.SELECT_FILE,
        payload: { file, fileName: file.name },
      }),
      []
    ),

    /** User explicitly chose a sample document */
    selectSample: useCallback(
      (fileName, sampleKey) => dispatch({
        type: ACTIONS.SELECT_SAMPLE,
        payload: { fileName, sampleKey },
      }),
      []
    ),

    /** User removed the selected file */
    clearFile: useCallback(
      () => dispatch({ type: ACTIONS.CLEAR_FILE }),
      []
    ),

    /** Update pipeline status (called by verification service) */
    setStatus: useCallback(
      (status) => dispatch({ type: ACTIONS.SET_STATUS, payload: status }),
      []
    ),

    /** Populate traveler fields from OCR response */
    setTraveler: useCallback(
      (travelerData) => dispatch({ type: ACTIONS.SET_TRAVELER, payload: travelerData }),
      []
    ),

    /** Set biometric results */
    setBiometrics: useCallback(
      (biometricData) => dispatch({ type: ACTIONS.SET_BIOMETRICS, payload: biometricData }),
      []
    ),

    /** Update verification check results */
    setChecks: useCallback(
      (checkUpdates) => dispatch({ type: ACTIONS.SET_CHECKS, payload: checkUpdates }),
      []
    ),

    /** Store Module 2 validation details and checksum evidence */
    setValidationDetail: useCallback(
      (validationData) => dispatch({ type: ACTIONS.SET_VALIDATION_DETAIL, payload: validationData }),
      []
    ),

    /** Store Module 3 forensic analysis summary */
    setForensicDetail: useCallback(
      (forensicData) => dispatch({ type: ACTIONS.SET_FORENSIC_DETAIL, payload: forensicData }),
      []
    ),

    /** Store Module 4 biometric analysis summary */
    setFaceDetail: useCallback(
      (faceData) => dispatch({ type: ACTIONS.SET_FACE_DETAIL, payload: faceData }),
      []
    ),

    /** Store Module 5 registry verification response */
    setRegistryDetail: useCallback(
      (registryData) => dispatch({ type: ACTIONS.SET_REGISTRY_DETAIL, payload: registryData }),
      []
    ),

    /** Reset biometrics back to neutral standby */
    resetBiometrics: useCallback(
      () => dispatch({ type: ACTIONS.RESET_BIOMETRICS }),
      []
    ),


    /** Set the top-level verification result. payload: { decision: DECISION.*, ... } */
    setResult: useCallback(
      (resultObj) => dispatch({ type: ACTIONS.SET_RESULT, payload: resultObj }),
      []
    ),

    /** Set forensic evidence */
    setForensicEvidence: useCallback(
      (evidence) => dispatch({ type: ACTIONS.SET_FORENSIC_EVIDENCE, payload: evidence }),
      []
    ),

    /** Set risk assessment */
    setRisk: useCallback(
      (riskData) => dispatch({ type: ACTIONS.SET_RISK, payload: riskData }),
      []
    ),

    /** Store backend-assigned session ID */
    setSessionId: useCallback(
      (id) => dispatch({ type: ACTIONS.SET_SESSION_ID, payload: id }),
      []
    ),

    /** Store a user-facing error message */
    setError: useCallback(
      (message) => dispatch({ type: ACTIONS.SET_ERROR, payload: message }),
      []
    ),

    /** Clear error state */
    clearError: useCallback(
      () => dispatch({ type: ACTIONS.CLEAR_ERROR }),
      []
    ),

    /** Full reset — keeps current document type */
    resetSession: useCallback(
      () => dispatch({ type: ACTIONS.RESET_SESSION }),
      []
    ),
  };

  return (
    <VerificationContext.Provider value={{ session, dispatch, actions }}>
      {children}
    </VerificationContext.Provider>
  );
}


