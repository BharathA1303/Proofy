/**
 * BiometricStatus.jsx
 *
 * Module 4: Face Verification + Presentation Attack Detection Interface.
 *
 * Architectural Guarantees:
 *   - Camera is NEVER activated automatically; requires explicit user action.
 *   - Uses actual navigator.mediaDevices.getUserMedia() browser camera stream.
 *   - Handles camera permission denials, device missing, and capture errors explicitly.
 *   - Captures real camera frames and multi-frame burst for PAD analysis.
 *   - Populates telemetry cards from real backend inference only — no fake percentages.
 *   - Keeps Anti-Spoof / Liveness score and Face Match score strictly separate.
 *   - Enterprise security workstation visual language (no dark/neon cyberpunk).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useVerification } from '../../state/verification/useVerification.js';
import { CHECK_STATUS, SESSION_STATUS } from '../../state/verification/initialState.js';
import { verifyBiometrics, runRegistryVerification } from '../../services/verificationApi.js';
import SectionHeader from '../common/SectionHeader.jsx';
import styles from './BiometricStatus.module.css';

function BiometricCard({ label, sublabel, value, description, statusText, statusBadgeClass, iconType }) {
  const hasValue = value !== null && value !== undefined;
  const display = hasValue ? `${value}%` : '--%';
  const percent = hasValue ? Math.min(Math.max(value, 0), 100) : 0;

  let scoreClass = styles.scoreNeutral;
  let barColorClass = styles.barNeutral;

  if (hasValue) {
    if (value >= 80) {
      scoreClass = styles.scoreHigh;
      barColorClass = styles.barGreen;
    } else if (value >= 50) {
      scoreClass = styles.scoreMedium;
      barColorClass = styles.barAmber;
    } else {
      scoreClass = styles.scoreLow;
      barColorClass = styles.barRed;
    }
  }

  return (
    <div className={styles.telemetryCard}>
      <div className={styles.cardHeader}>
        <div className={styles.labelGroup}>
          <span className={styles.scoreLabel}>{label}</span>
          <span className={styles.sublabel}>{sublabel}</span>
        </div>
        <div className={styles.iconBox} aria-hidden="true">
          {iconType === 'face' ? (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 10h.01" />
              <path d="M15 10h.01" />
              <path d="M10 14a2 2 0 0 0 4 0" />
              <rect x="3" y="3" width="18" height="18" rx="4" />
            </svg>
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
              <path d="M2 12h5" />
              <path d="M17 12h5" />
              <circle cx="12" cy="12" r="7" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          )}
        </div>
      </div>

      <div className={styles.scoreRow}>
        <span
          className={`${styles.scoreValue} ${scoreClass}`}
          aria-label={`${label}: ${hasValue ? display : 'Not available'}`}
        >
          {display}
        </span>
        <span className={`${styles.statusIndicator} ${statusBadgeClass || ''}`}>
          {statusText || 'STANDBY'}
        </span>
      </div>

      {/* Biometric telemetry meter */}
      <div className={styles.meterTrack} aria-hidden="true">
        <div
          className={`${styles.meterFill} ${barColorClass}`}
          style={{ width: `${percent}%` }}
        />
      </div>

      <span className={styles.scoreDescription}>
        {description || (hasValue ? 'Biometric vector verified' : 'Awaiting live camera capture')}
      </span>
    </div>
  );
}

export default function BiometricStatus() {
  const { session, actions } = useVerification();
  const { biometrics, checks, sessionId, file, documentType } = session;

  const [cameraActive, setCameraActive] = useState(false);
  const [cameraStatus, setCameraStatus] = useState('INITIALIZING CAMERA');
  const [isProcessing, setIsProcessing] = useState(false);
  const [cameraError, setCameraError] = useState(null);

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);

  // Stop camera stream safely
  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setCameraActive(false);
  }, []);

  // Cleanup camera when component unmounts or document type switches
  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, [documentType, stopCamera]);

  // Start camera on explicit user button click
  const handleStartCamera = async () => {
    setCameraError(null);
    setCameraStatus('INITIALIZING CAMERA');

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setCameraError({
        code: 'CAMERA_NOT_SUPPORTED',
        message: 'Browser does not support mediaDevices video capture.',
      });
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          facingMode: 'user',
        },
        audio: false,
      });

      streamRef.current = stream;
      setCameraActive(true);
      setCameraStatus('POSITION FACE INSIDE FRAME');

      // Connect stream to video element on next tick
      setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch((err) => {
            console.warn('Video play error:', err);
          });
        }
      }, 50);

    } catch (err) {
      console.error('Camera initialization error:', err);
      let errCode = 'CAMERA_INITIALIZATION_FAILED';
      let errMsg = 'Failed to initialize camera capture device.';

      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        errCode = 'CAMERA_PERMISSION_DENIED';
        errMsg = 'Camera permission was denied. Please allow camera access in your browser settings to proceed.';
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        errCode = 'CAMERA_NOT_AVAILABLE';
        errMsg = 'No video capture device found. Please connect a webcam.';
      } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
        errCode = 'CAMERA_NOT_AVAILABLE';
        errMsg = 'Camera is currently in use by another application.';
      }

      setCameraError({ code: errCode, message: errMsg });
      stopCamera();
    }
  };

  // Capture frame from video feed
  const captureFrameBlob = (videoEl, canvasEl) => {
    return new Promise((resolve) => {
      if (!videoEl || !canvasEl) {
        resolve(null);
        return;
      }
      const vw = videoEl.videoWidth || 640;
      const vh = videoEl.videoHeight || 480;
      canvasEl.width = vw;
      canvasEl.height = vh;

      const ctx = canvasEl.getContext('2d');
      ctx.drawImage(videoEl, 0, 0, vw, vh);

      canvasEl.toBlob((blob) => {
        resolve(blob);
      }, 'image/jpeg', 0.92);
    });
  };

  // Handle capture & submission
  const handleCaptureAndVerify = async () => {
    if (!videoRef.current || !canvasRef.current || isProcessing) return;

    setIsProcessing(true);
    setCameraStatus('HOLD STILL · PROCESSING...');
    setCameraError(null);

    try {
      // 1. Capture primary frame
      const primaryBlob = await captureFrameBlob(videoRef.current, canvasRef.current);
      if (!primaryBlob) {
        throw new Error('Failed to acquire frame from video stream.');
      }

      // 2. Capture a short 2-frame sequence spaced by 120ms for multi-frame liveness consistency
      await new Promise((r) => setTimeout(r, 120));
      const seqBlob1 = await captureFrameBlob(videoRef.current, canvasRef.current);
      await new Promise((r) => setTimeout(r, 120));
      const seqBlob2 = await captureFrameBlob(videoRef.current, canvasRef.current);

      const sequenceBlobs = [seqBlob1, seqBlob2].filter(Boolean);

      // Stop camera tracks immediately after capture (privacy best-practice)
      stopCamera();

      // 3. Send to backend Module 4 verification endpoint
      const response = await verifyBiometrics(
        sessionId || 'session-default',
        documentType,
        primaryBlob,
        sequenceBlobs,
        file // fallback if session cache expired
      );

      // 4. Update session context with response
      actions.setFaceDetail(response);

      const faceSim = response.face_match?.similarity;
      const antiScore = response.anti_spoof?.score;

      const faceMatchPercent = (faceSim !== null && faceSim !== undefined)
        ? Math.round(faceSim * 100)
        : null;

      const livenessPercent = (antiScore !== null && antiScore !== undefined)
        ? Math.round(antiScore * 100)
        : null;

      actions.setBiometrics({
        faceMatch: faceMatchPercent,
        liveness: livenessPercent,
        status: response.status,
        documentFace: response.document_face,
        liveFace: response.live_face,
        antiSpoof: response.anti_spoof,
        faceMatchResult: response.face_match,
        secondaryPad: response.secondary_pad,
        overallAssessment: response.overall_assessment,
        summary: response.summary,
      });

      // 5. Update inspection check badge
      let checkResult = CHECK_STATUS.WARNING;
      if (response.overall_assessment === 'FACE_MATCH') {
        checkResult = CHECK_STATUS.PASSED;
      } else if (
        response.overall_assessment === 'FACE_MISMATCH' ||
        response.overall_assessment === 'SUSPECTED_SPOOF' ||
        response.overall_assessment === 'DOCUMENT_FACE_UNAVAILABLE' ||
        response.overall_assessment === 'LIVE_FACE_UNAVAILABLE'
      ) {
        checkResult = CHECK_STATUS.FAILED;
      }

      actions.setChecks({
        faceVerification: checkResult,
      });

      // ── Phase 5: MODULE 5 — REGISTRY VERIFICATION (auto-triggered after M4) ─────
      // Fires automatically once M4 completes (regardless of face outcome).
      // Absence of biometrics ≠ document invalid. The registry is an independent
      // evidence source that must not be gated on M4 success.
      // On failure: sets registryVerification to 'warning'; never fails silently.
      try {
        const registryResponse = await runRegistryVerification(
          sessionId || 'session-default',
          documentType,
        );
        actions.setRegistryDetail(registryResponse);

        // Map registry status to check badge
        const regStatus = registryResponse?.registry?.status;
        let registryCheckResult = CHECK_STATUS.WARNING;
        if (regStatus === 'MATCHED') {
          registryCheckResult = CHECK_STATUS.PASSED;
        } else if (regStatus === 'REVOKED' || regStatus === 'MISMATCH' || regStatus === 'SUSPENDED' || regStatus === 'INVALID') {
          registryCheckResult = CHECK_STATUS.FAILED;
        } else if (regStatus === 'NOT_FOUND' || regStatus === 'EXPIRED') {
          registryCheckResult = CHECK_STATUS.WARNING;
        } else if (regStatus === 'UNAVAILABLE' || regStatus === 'TIMEOUT' || regStatus === 'PROVIDER_ERROR') {
          registryCheckResult = CHECK_STATUS.WARNING;
        }

        actions.setChecks({
          registryVerification: registryCheckResult,
        });
      } catch (regErr) {
        console.warn('Module 5 registry verification error (non-fatal):', regErr);
        // Registry failure must not disrupt M1–4 results
        actions.setChecks({
          registryVerification: CHECK_STATUS.WARNING,
        });
      }

      // If backend returned quality or detection error, surface clear instructions
      if (response.overall_assessment !== 'FACE_MATCH' && response.overall_assessment !== 'FACE_MISMATCH') {
        const docErr = response.document_face?.error;
        const liveErr = response.live_face?.error;
        const padStatus = response.anti_spoof?.status;

        if (liveErr) {
          setCameraError({
            code: liveErr,
            message: response.live_face?.quality_details?.explanation || response.summary,
          });
        } else if (docErr) {
          setCameraError({
            code: docErr,
            message: response.document_face?.quality_details?.explanation || response.summary,
          });
        } else if (padStatus === 'suspected_spoof') {
          setCameraError({
            code: 'LIVENESS_FAILED',
            message: response.anti_spoof?.explanation || 'Presentation attack suspected. Capture exhibits spoof anomalies.',
          });
        }
      }

    } catch (err) {
      console.error('Biometric verification error:', err);
      setCameraError({
        code: 'PROCESSING_ERROR',
        message: err.message || 'Biometric processing encountered an error. Please try again.',
      });
      actions.setChecks({
        faceVerification: CHECK_STATUS.FAILED,
      });
    } finally {
      setIsProcessing(false);
      stopCamera();
    }
  };

  const isModuleReady = Boolean(session.file || session.status !== SESSION_STATUS.STANDBY);
  const hasCompletedResult = Boolean(session.faceDetail || biometrics.overallAssessment);

  // Status text & styling for telemetry cards
  let matchBadgeText = 'STANDBY';
  let matchBadgeClass = '';
  if (biometrics.faceMatchResult?.status) {
    const s = biometrics.faceMatchResult.status;
    matchBadgeText = s.toUpperCase();
    if (s === 'match') matchBadgeClass = styles.badgeMatch;
    else if (s === 'no_match') matchBadgeClass = styles.badgeMismatch;
    else matchBadgeClass = styles.badgeWarn;
  }

  let livenessBadgeText = 'STANDBY';
  let livenessBadgeClass = '';
  if (biometrics.antiSpoof?.status) {
    const s = biometrics.antiSpoof.status;
    livenessBadgeText = s.replace(/_/g, ' ').toUpperCase();
    if (s === 'pass') livenessBadgeClass = styles.badgeMatch;
    else if (s === 'suspected_spoof') livenessBadgeClass = styles.badgeMismatch;
    else livenessBadgeClass = styles.badgeWarn;
  }

  // Hide empty standby placeholders when no document has been selected/processed
  if (session.status === SESSION_STATUS.STANDBY && !cameraActive && !hasCompletedResult) {
    return null;
  }

  return (
    <div className={styles.section} aria-label="Biometric verification and live camera capture">
      <SectionHeader
        title="Biometric Telemetry"
        subtitle="Facial vector matching & presentation attack detection"
        level={3}
      />

      {/* Hidden off-screen canvas for frame capture */}
      <canvas ref={canvasRef} style={{ display: 'none' }} aria-hidden="true" />

      {/* ── 1. Live Camera Active View ── */}
      {cameraActive && (
        <div className={styles.cameraCard}>
          <div className={styles.cameraHeader}>
            <div className={styles.cameraTitleGroup}>
              <span className={styles.cameraTitle}>Live Camera Inspection</span>
            </div>
            <span className={styles.cameraInstruction}>{cameraStatus}</span>
          </div>

          <div className={styles.cameraFeedContainer}>
            <video
              ref={videoRef}
              className={styles.cameraVideo}
              autoPlay
              playsInline
              muted
              aria-label="Live camera preview feed"
            />
            {/* Professional workstation target oval */}
            <div className={styles.framingGuide} aria-hidden="true" />
            <div className={styles.framingLabel}>Position face inside frame</div>
          </div>

          <div className={styles.cameraControls}>
            <button
              type="button"
              className={styles.cancelBtn}
              onClick={stopCamera}
              disabled={isProcessing}
            >
              Cancel
            </button>
            <button
              type="button"
              className={styles.captureBtn}
              onClick={handleCaptureAndVerify}
              disabled={isProcessing}
            >
              {isProcessing ? 'Processing Biometrics...' : 'Capture & Verify'}
            </button>
          </div>
        </div>
      )}

      {/* ── 2. Camera / Quality Error Banner ── */}
      {cameraError && !cameraActive && (
        <div className={styles.errorCard} role="alert">
          <div className={styles.errorTitle}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>{cameraError.code.replace(/_/g, ' ')}</span>
          </div>
          <p className={styles.errorText}>{cameraError.message}</p>
          <button
            type="button"
            className={styles.retryBtn}
            onClick={handleStartCamera}
          >
            Retry Capture
          </button>
        </div>
      )}

      {/* ── 3. Initial / Ready Standby Prompt (Before Camera Start) ── */}
      {!cameraActive && !hasCompletedResult && (
        <div className={styles.standbyCard}>
          <div className={styles.standbyHeader}>
            <div className={styles.standbyIconBox} aria-hidden="true">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                <circle cx="12" cy="13" r="4" />
              </svg>
            </div>
            <div className={styles.standbyText}>
              <span className={styles.standbyTitle}>Module 4: Live Face Verification (ArcFace + MiniFASNet)</span>
              <span className={styles.standbyDesc}>
                {isModuleReady
                  ? 'Document loaded. Launch browser webcam to scan the standing traveler and match against the document photograph.'
                  : 'Awaiting document upload before initiating live camera capture.'}
              </span>
            </div>
          </div>

          <div className={styles.actionRow}>
            <button
              type="button"
              className={styles.startBtn}
              onClick={handleStartCamera}
              disabled={!isModuleReady}
              title={isModuleReady ? 'Initialize browser camera for live facial matching' : 'Upload or load a document first'}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                <circle cx="12" cy="13" r="4" />
              </svg>
              <span>Launch Live Camera Scan</span>
            </button>
          </div>
        </div>
      )}

      {/* ── 4. Telemetry Meters (Face Match & Anti-Spoofing) ── */}
      <div className={styles.scores}>
        <BiometricCard
          label="Facial Vector Match"
          sublabel={
            biometrics.faceMatchResult?.embedding_model
              ? `ArcFace (${biometrics.faceMatchResult.embedding_model}) 512-D`
              : 'ArcFace 512-D Cosine Match'
          }
          value={biometrics.faceMatch}
          statusText={matchBadgeText}
          statusBadgeClass={matchBadgeClass}
          description={biometrics.faceMatchResult?.explanation || null}
          iconType="face"
        />
        <BiometricCard
          label="Anti-Spoof / Liveness"
          sublabel={
            biometrics.antiSpoof?.model
              ? `Primary Deep PAD (${biometrics.antiSpoof.model})`
              : 'Deep MiniFASNetV2 PAD'
          }
          value={biometrics.liveness}
          statusText={livenessBadgeText}
          statusBadgeClass={livenessBadgeClass}
          description={biometrics.antiSpoof?.explanation || null}
          iconType="liveness"
        />
      </div>

      {/* ── 4b. Secondary Defensive Telemetry (Explainable Optical Signals) ── */}
      {biometrics.secondaryPad && (
        <div className={styles.secondaryPanel} aria-label="Secondary Defensive Optical Telemetry">
          <div className={styles.secondaryHeader}>
            <div className={styles.secondaryTitleGroup}>
              <span className={styles.secondaryTitle}>Secondary Defensive Optical Telemetry</span>
              <span className={styles.secondaryTag}>MULTI-CUE OPTICAL</span>
            </div>
            <span className={`${styles.statusIndicator} ${biometrics.secondaryPad.status === 'PASS' ? styles.badgeMatch : styles.badgeWarn}`}>
              {biometrics.secondaryPad.status}
            </span>
          </div>
          <div className={styles.secondaryGrid}>
            <div className={styles.secondaryItem}>
              <span className={styles.secondaryItemLabel}>2D FFT Moiré</span>
              <span className={styles.secondaryItemValue}>
                {Math.round(biometrics.secondaryPad.frequency_domain_score * 100)}%
              </span>
            </div>
            <div className={styles.secondaryItem}>
              <span className={styles.secondaryItemLabel}>Chroma / Texture</span>
              <span className={styles.secondaryItemValue}>
                {Math.round(biometrics.secondaryPad.color_texture_score * 100)}%
              </span>
            </div>
            <div className={styles.secondaryItem}>
              <span className={styles.secondaryItemLabel}>Specular Reflection</span>
              <span className={styles.secondaryItemValue}>
                {Math.round(biometrics.secondaryPad.specular_reflection_score * 100)}%
              </span>
            </div>
            {biometrics.secondaryPad.temporal_variance_score !== null && biometrics.secondaryPad.temporal_variance_score !== undefined && (
              <div className={styles.secondaryItem}>
                <span className={styles.secondaryItemLabel}>Temporal Micro-Variance</span>
                <span className={styles.secondaryItemValue}>
                  {Math.round(biometrics.secondaryPad.temporal_variance_score * 100)}%
                </span>
              </div>
            )}
          </div>
          {biometrics.secondaryPad.telemetry_notes && biometrics.secondaryPad.telemetry_notes.length > 0 && (
            <ul className={styles.secondaryNotesList}>
              {biometrics.secondaryPad.telemetry_notes.map((note, idx) => (
                <li key={idx}>{note}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* ── 5. Completed Result Banner & Re-capture Option ── */}
      {hasCompletedResult && !cameraActive && (
        <div className={styles.resultBanner}>
          <div className={styles.resultTextGroup}>
            <span className={styles.resultTitle}>
              Biometric Assessment: {biometrics.overallAssessment ? biometrics.overallAssessment.replace(/_/g, ' ') : 'COMPLETED'}
            </span>
            <span className={styles.resultDetail}>
              {biometrics.summary || 'Biometric vector matching and liveness telemetry verified.'}
            </span>
          </div>
          <button
            type="button"
            className={styles.recaptureBtn}
            onClick={handleStartCamera}
          >
            Re-Capture Face
          </button>
        </div>
      )}
    </div>
  );
}
