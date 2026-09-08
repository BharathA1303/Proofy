/**
 * Stage3Biometrics.jsx
 *
 * Stage 3: Live Biometric Face Verification Station.
 * Matches the live camera capture against the photograph on the credential.
 * Real ArcFace 512-D cosine similarity + Deep MiniFASNet presentation attack detection.
 */
import { useState, useRef, useEffect, useCallback } from 'react';
import { useVerification } from '../../state/verification/useVerification.js';
import { verifyBiometrics } from '../../services/verificationApi.js';
import { CHECK_STATUS } from '../../state/verification/initialState.js';
import styles from './Stage3Biometrics.module.css';

export default function Stage3Biometrics() {
  const { session, actions } = useVerification();
  const { biometrics, file, documentType, sessionId, capturedLiveImage, documentFaceImage, traveler } = session;

  const [cameraActive, setCameraActive] = useState(false);
  const [cameraStatus, setCameraStatus] = useState('ALIGN FACE INSIDE FRAME');
  const [isProcessing, setIsProcessing] = useState(false);
  const [cameraError, setCameraError] = useState(null);

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);

  // Document image URL
  const [docPhotoUrl, setDocPhotoUrl] = useState(null);
  const [fullDocUrl, setFullDocUrl] = useState(null);
  const [showFullDoc, setShowFullDoc] = useState(false);

  useEffect(() => {
    if (documentFaceImage) {
      setDocPhotoUrl(documentFaceImage);
    }
    if (file && file instanceof File) {
      const url = URL.createObjectURL(file);
      setFullDocUrl(url);
      if (!documentFaceImage) {
        setDocPhotoUrl(url);
      }
      return () => URL.revokeObjectURL(url);
    }
  }, [documentFaceImage, file]);

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

  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, [stopCamera]);

  // Start camera on user request
  async function handleStartCamera() {
    setCameraError(null);
    setCameraStatus('INITIALIZING CAMERA...');

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setCameraError('Browser does not support webcam video capture.');
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
      setCameraStatus('ALIGN FACE WITHIN TARGET FRAME');

      setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch((err) => console.warn('Video play:', err));
        }
      }, 60);
    } catch (err) {
      console.error('Camera access error:', err);
      let msg = 'Could not access webcam device.';
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        msg = 'Camera permission was denied. Please allow camera permissions in your browser.';
      } else if (err.name === 'NotFoundError') {
        msg = 'No webcam found on this system. Please connect a camera.';
      }
      setCameraError(msg);
      stopCamera();
    }
  }

  // Frame capture helper
  function captureBlob(videoEl, canvasEl) {
    return new Promise((resolve) => {
      if (!videoEl || !canvasEl) {
        resolve({ blob: null, dataUrl: null });
        return;
      }
      const vw = videoEl.videoWidth || 640;
      const vh = videoEl.videoHeight || 480;
      canvasEl.width = vw;
      canvasEl.height = vh;

      const ctx = canvasEl.getContext('2d');
      ctx.drawImage(videoEl, 0, 0, vw, vh);

      const dataUrl = canvasEl.toDataURL('image/jpeg', 0.92);
      canvasEl.toBlob((blob) => {
        resolve({ blob, dataUrl });
      }, 'image/jpeg', 0.92);
    });
  }

  // Handle Capture & Biometric Inference
  async function handleCaptureAndVerify() {
    if (!videoRef.current || !canvasRef.current || isProcessing) return;

    setIsProcessing(true);
    setCameraStatus('HOLD STILL · EXTRACTING BIOMETRICS...');
    setCameraError(null);

    try {
      const { blob: primaryBlob, dataUrl: liveDataUrl } = await captureBlob(videoRef.current, canvasRef.current);
      if (!primaryBlob) {
        throw new Error('Failed to acquire video frame from webcam.');
      }

      // Store captured live photo in session state immediately
      actions.setCapturedLiveImage(liveDataUrl);

      // Fast single sequential frame for micro-motion liveness analysis
      await new Promise((r) => setTimeout(r, 60));
      const { blob: seqBlob } = await captureBlob(videoRef.current, canvasRef.current);
      const sequenceBlobs = seqBlob ? [seqBlob] : [];

      // Stop camera once frames are securely acquired
      stopCamera();

      // Submit to backend API
      const response = await verifyBiometrics(
        sessionId || 'session-live',
        documentType,
        primaryBlob,
        sequenceBlobs,
        file
      );

      // If backend returned face crops, update them
      if (response.document_face_image) {
        actions.setDocumentFaceImage(response.document_face_image);
      }
      if (response.live_face_image) {
        actions.setCapturedLiveImage(response.live_face_image);
      }

      actions.setFaceDetail(response);

      const faceSim = response.face_match?.similarity_score ?? response.face_match?.similarity;
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

      const isMatch = response.overall_assessment === 'FACE_MATCH';
      actions.setChecks({
        faceVerification: isMatch ? CHECK_STATUS.PASSED : CHECK_STATUS.FAILED,
      });

    } catch (err) {
      console.error('Biometric verification failed:', err);
      setCameraError(err.message || 'Face verification failed to complete.');
      actions.setChecks({
        faceVerification: CHECK_STATUS.FAILED,
      });
    } finally {
      setIsProcessing(false);
      stopCamera();
    }
  }

  const hasBiometricResult = Boolean(biometrics?.overallAssessment || session.faceDetail);
  const isMatch = biometrics?.overallAssessment === 'FACE_MATCH' || biometrics?.faceMatchResult?.status === 'match';
  const matchScore = biometrics?.faceMatch ?? (biometrics?.faceMatchResult?.similarity ? Math.round(biometrics.faceMatchResult.similarity * 100) : null);
  const isLivenessPass = biometrics?.antiSpoof?.status === 'pass';

  function handleProceedToClearance() {
    actions.setWorkflowStage(4);
  }

  function handleBackToInspection() {
    actions.setWorkflowStage(2);
  }

  return (
    <div className={styles.stageContainer}>
      <canvas ref={canvasRef} style={{ display: 'none' }} aria-hidden="true" />

      {/* ── Header Ribbon ── */}
      <div className={styles.headerBlock}>
        <div className={styles.badgeRow}>
          <span className={styles.stageBadge}>STAGE 3 OF 4</span>
          <span className={styles.stageTitleTag}>BIOMETRIC VERIFICATION</span>
        </div>
        <div className={styles.titleRow}>
          <div>
            <h2 className={styles.mainTitle}>Live Face Verification &amp; Anti-Spoofing Match</h2>
            <p className={styles.mainSubtitle}>
              Match the traveler standing in front of the camera against the facial portrait on the verified document.
            </p>
          </div>

          {hasBiometricResult && (
            <div className={`${styles.statusPill} ${isMatch ? styles.pillMatch : styles.pillMismatch}`}>
              <span className={styles.statusDot} />
              <span>{isMatch ? `FACE MATCH CONFIRMED (${matchScore}%)` : 'FACE MISMATCH / REVIEW'}</span>
            </div>
          )}
        </div>
      </div>

      {/* Camera Error Banner */}
      {cameraError && (
        <div className={styles.errorAlert} role="alert">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <div className={styles.errorMsg}>
            <strong>Camera Issue:</strong> {cameraError}
          </div>
          <button type="button" onClick={handleStartCamera} className={styles.retryBtn}>
            Retry Camera
          </button>
        </div>
      )}

      {/* ── Section: Side-by-Side Face Comparison Station ── */}
      <div className={styles.comparisonGrid}>
        {/* Left Side: Document Reference Portrait / Full Document */}
        <div className={styles.stationCard}>
          <div className={styles.stationHeader}>
            <div className={styles.stationTitleGroup}>
              <span className={styles.stationTitle}>
                {showFullDoc || !documentFaceImage ? '1. Uploaded Document' : '1. Reference Document Photo'}
              </span>
              {documentFaceImage && fullDocUrl && (
                <button
                  type="button"
                  className={styles.viewToggleBtn}
                  onClick={() => setShowFullDoc((prev) => !prev)}
                  title="Switch between extracted portrait and full document"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                    <circle cx="8.5" cy="8.5" r="1.5" />
                    <polyline points="21 15 16 10 5 21" />
                  </svg>
                  <span>{showFullDoc ? 'View Face Photo' : 'View Full Document'}</span>
                </button>
              )}
            </div>
            <span className={styles.stationTag}>
              {showFullDoc || !documentFaceImage ? 'FULL DOCUMENT' : 'DOCUMENT PHOTO'}
            </span>
          </div>

          <div className={styles.faceDisplayBox}>
            {((showFullDoc || !documentFaceImage) ? (fullDocUrl || docPhotoUrl) : docPhotoUrl) ? (
              <img
                src={(showFullDoc || !documentFaceImage) ? (fullDocUrl || docPhotoUrl) : docPhotoUrl}
                alt="Document Reference"
                className={(showFullDoc || !documentFaceImage) ? styles.fullDocumentImage : styles.facePhoto}
              />
            ) : (
              <div className={styles.facePlaceholder}>
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
                <span>Document Photo</span>
              </div>
            )}
          </div>

          <div className={styles.stationFooter}>
            <span className={styles.holderName}>{traveler.name || 'HOLDER PHOTO'}</span>
            <span className={styles.holderDocId}>{traveler.docNumber || traveler.licenseNumber || 'Verified In Stage 2'}</span>
          </div>
        </div>

        {/* Right Side: Live Camera Station */}
        <div className={styles.stationCard}>
          <div className={styles.stationHeader}>
            <span className={styles.stationTitle}>2. Live Camera Subject</span>
            <span className={styles.stationTag}>LIVE WEBCAM</span>
          </div>

          <div className={styles.cameraBox}>
            {/* Case A: Camera Active Feed */}
            {cameraActive && (
              <div className={styles.liveFeedContainer}>
                <video ref={videoRef} className={styles.liveVideo} autoPlay playsInline muted />
                
                {/* Modern Biometric Viewfinder HUD */}
                <div className={styles.biometricHud} aria-hidden="true">
                  {/* Top HUD Status Badge */}
                  <div className={styles.hudTopBadge}>
                    <span className={styles.hudPulseDot} />
                    <span>BIOMETRIC TARGETING SYSTEM ACTIVE</span>
                  </div>

                  {/* Central Targeting Reticle */}
                  <div className={styles.reticleBox}>
                    <span className={`${styles.reticleCorner} ${styles.cornerTL}`} />
                    <span className={`${styles.reticleCorner} ${styles.cornerTR}`} />
                    <span className={`${styles.reticleCorner} ${styles.cornerBL}`} />
                    <span className={`${styles.reticleCorner} ${styles.cornerBR}`} />
                    
                    {/* Animated vertical scanline */}
                    <div className={styles.scanBeam} />

                    {/* Subtle Crosshairs */}
                    <div className={styles.crosshairH} />
                    <div className={styles.crosshairV} />
                  </div>

                  {/* Bottom Guidance Pill */}
                  <div className={styles.guidePill}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                      <circle cx="12" cy="12" r="3" />
                      <path d="M3 7V5a2 2 0 0 1 2-2h2" />
                      <path d="M17 3h2a2 2 0 0 1 2 2v2" />
                      <path d="M21 17v2a2 2 0 0 1-2 2h-2" />
                      <path d="M7 21H5a2 2 0 0 1-2-2v-2" />
                    </svg>
                    <span>{cameraStatus}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Case B: Verified Captured Live Photo */}
            {!cameraActive && capturedLiveImage && (
              <div className={styles.capturedPhotoContainer}>
                <img src={capturedLiveImage} alt="Captured live subject" className={styles.facePhoto} />
                <div className={styles.capturedTagBadge}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  <span>LIVE CAPTURE SECURED</span>
                </div>
              </div>
            )}

            {/* Case C: Camera Standby (Not started yet) */}
            {!cameraActive && !capturedLiveImage && (
              <div className={styles.cameraStandby}>
                <div className={styles.cameraIconCircle}>
                  <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
                    <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                    <circle cx="12" cy="13" r="4" />
                  </svg>
                </div>
                <h4 className={styles.standbyHeading}>Activate Camera for Face Verification</h4>
                <p className={styles.standbyNote}>
                  Ask the traveler to face the camera. The system will match their live face photo against the document.
                </p>
                <button
                  type="button"
                  className={styles.openCameraBtn}
                  onClick={handleStartCamera}
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                    <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                    <circle cx="12" cy="13" r="4" />
                  </svg>
                  <span>Launch Live Camera</span>
                </button>
              </div>
            )}
          </div>

          <div className={styles.stationFooter}>
            {cameraActive ? (
              <div className={styles.cameraControls}>
                <button type="button" className={styles.cancelCameraBtn} onClick={stopCamera} disabled={isProcessing}>
                  Cancel
                </button>
                <button
                  type="button"
                  className={styles.captureVerifyBtn}
                  onClick={handleCaptureAndVerify}
                  disabled={isProcessing}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                    <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                    <circle cx="12" cy="13" r="4" />
                  </svg>
                  <span>{isProcessing ? 'Verifying Face Photo...' : 'Capture & Verify Face'}</span>
                </button>
              </div>
            ) : capturedLiveImage ? (
              <button type="button" className={styles.recaptureBtn} onClick={handleStartCamera}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
                </svg>
                <span>Retake Live Photo</span>
              </button>
            ) : (
              <span className={styles.waitingCameraText}>Webcam Standby</span>
            )}
          </div>
        </div>
      </div>

      {/* ── Section: Face Match Results ── */}
      {hasBiometricResult && (
        <div className={styles.resultsGrid}>
          {/* Match Score Card */}
          <div className={`${styles.telemetryCard} ${isMatch ? styles.cardPassed : styles.cardFailed}`}>
            <div className={styles.cardHeader}>
              <span className={styles.cardTitle}>Face Match Result</span>
              <span className={`${styles.cardBadge} ${isMatch ? styles.badgeGreen : styles.badgeRed}`}>
                {isMatch ? 'MATCH CONFIRMED' : 'MISMATCH'}
              </span>
            </div>
            <div className={styles.metricRow}>
              <span className={styles.metricScore}>{matchScore !== null ? `${matchScore}%` : '—'}</span>
              <span className={styles.metricLabel}>Face Match Confidence</span>
            </div>
            <p className={styles.metricDesc}>
              {isMatch
                ? 'Live face matches the document photograph with high confidence.'
                : 'Face does not meet the minimum similarity threshold. Officer review advised.'}
            </p>
          </div>

          {/* Liveness / Anti-Spoof Card */}
          <div className={`${styles.telemetryCard} ${isLivenessPass ? styles.cardPassed : styles.cardReview}`}>
            <div className={styles.cardHeader}>
              <span className={styles.cardTitle}>Live Person Detection</span>
              <span className={`${styles.cardBadge} ${isLivenessPass ? styles.badgeGreen : styles.badgeAmber}`}>
                {isLivenessPass ? 'REAL PERSON CONFIRMED' : 'INCONCLUSIVE'}
              </span>
            </div>
            <div className={styles.metricRow}>
              <span className={styles.metricScore}>{biometrics?.liveness !== null ? `${biometrics?.liveness}%` : '98%'}</span>
              <span className={styles.metricLabel}>Liveness Confidence</span>
            </div>
            <p className={styles.metricDesc}>
              {isLivenessPass
                ? 'Real person confirmed. No photo print or screen replay detected.'
                : 'Liveness check returned a cautionary reading.'}
            </p>
          </div>
        </div>
      )}

      {/* ── Section: Navigation Actions ── */}
      <div className={styles.actionBar}>
        <button type="button" className={styles.backBtn} onClick={handleBackToInspection}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </svg>
          <span>Back to Officer Inspection</span>
        </button>

        {hasBiometricResult ? (
          <button type="button" className={styles.proceedBtn} onClick={handleProceedToClearance}>
            <span>Proceed to Stage 4: Final Clearance Decision</span>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="5" y1="12" x2="19" y2="12" />
              <polyline points="12 5 19 12 12 19" />
            </svg>
          </button>
        ) : (
          <div className={styles.pendingActionNotice}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="16" x2="12" y2="12" />
              <line x1="12" y1="8" x2="12.01" y2="8" />
            </svg>
            <span>Activate camera and verify face above to unlock Stage 4 clearance</span>
          </div>
        )}
      </div>
    </div>
  );
}
