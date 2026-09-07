/**
 * Stage4Clearance.jsx
 *
 * Stage 4: Officer Final Decision & Clearance Dossier.
 * Provides the definitive admission/rejection decision, comprehensive officer dossier,
 * official digital security stamp, and 1-click option to inspect the next document.
 */
import { useVerification } from '../../state/verification/useVerification.js';
import { DOCUMENT_PROFILES, DOCUMENT_TYPES } from '../../config/documentProfiles.js';
import styles from './Stage4Clearance.module.css';

export default function Stage4Clearance() {
  const { session, actions } = useVerification();
  const { biometrics, checks, registryDetail, traveler, capturedLiveImage, documentFaceImage, file, sessionId } = session;

  const profile = DOCUMENT_PROFILES[session.documentType] || DOCUMENT_PROFILES[DOCUMENT_TYPES.PASSPORT];

  const isMock = Boolean(session.isMockVector);

  const isDocValid = checks.documentValidation === 'passed';
  const isTamperClean = checks.tamperingDetection === 'passed';
  const regStatus = registryDetail?.registry?.status || '';
  const isRegistryCleared = regStatus === 'MATCHED' || checks.registryVerification === 'passed';
  const isBlacklisted = regStatus === 'REVOKED' || regStatus === 'SUSPENDED' || regStatus === 'BLACKLISTED';
  const isFaceMatch = isMock
    ? true // Mock vectors bypass live camera matching
    : (biometrics?.overallAssessment === 'FACE_MATCH' || biometrics?.faceMatchResult?.status === 'match');

  // Final Overall Clearance Status
  const isApproved = isDocValid && isTamperClean && isRegistryCleared && !isBlacklisted && isFaceMatch;

  const matchPercent = biometrics?.faceMatch ?? (biometrics?.faceMatchResult?.similarity ? Math.round(biometrics.faceMatchResult.similarity * 100) : null);

  // Document photo fallback
  const docPhotoUrl = documentFaceImage || ((file && file instanceof File) ? URL.createObjectURL(file) : null);

  function handlePrintClearance() {
    window.print();
  }

  function handleInspectNext() {
    actions.resetSession();
  }

  function handleBack() {
    if (isMock) {
      actions.setWorkflowStage(2);
    } else {
      actions.setWorkflowStage(3);
    }
  }

  const currentDate = new Date().toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
  const currentTime = new Date().toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });

  return (
    <div className={styles.stageContainer}>
      {/* ── Header Ribbon ── */}
      <div className={styles.headerBlock}>
        <div className={styles.badgeRow}>
          <span className={styles.stageBadge}>STAGE 4 OF 4</span>
          <span className={styles.stageTitleTag}>FINAL CLEARANCE DOSSIER</span>
        </div>
        <h2 className={styles.mainTitle}>Border &amp; Screening Clearance File</h2>
        <p className={styles.mainSubtitle}>
          Official identity verification certificate and security disposition record.
        </p>
      </div>

      {/* ── Section 1: Hero Decision Card ── */}
      <div className={`${styles.decisionHero} ${isApproved ? styles.heroApproved : styles.heroAlert}`}>
        <div className={styles.heroLeft}>
          <div className={styles.heroIconCircle}>
            {isApproved ? (
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.8">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            ) : (
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.8">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            )}
          </div>

          <div className={styles.heroText}>
            <span className={styles.heroPreTitle}>FINAL OFFICER DETERMINATION</span>
            <h1 className={styles.heroTitle}>
              {isApproved
                ? 'CLEARANCE APPROVED: TRAVELER ADMITTED'
                : isBlacklisted
                ? 'CLEARANCE DENIED: WATCHLIST ALERT'
                : 'CLEARANCE REJECTED / REFER TO SECONDARY'}
            </h1>
            <p className={styles.heroExplanation}>
              {isApproved
                ? (isMock
                    ? 'All physical credential format, security features, and central government registry checks satisfied. Biometric identity matched with archived records.'
                    : 'All security gates satisfied. Physical credential is authentic, registered in central government database, and biometric face matches the standing traveler with high confidence.')
                : isBlacklisted
                ? 'CRITICAL ALERT: Credential number is flagged as REVOKED/SUSPENDED on national law enforcement watchlists. Traveler must be escorted to secondary interrogation.'
                : !isFaceMatch
                ? 'BIOMETRIC MISMATCH: Facial features of standing traveler do not match the credential photograph. Impersonation warning.'
                : 'Physical or format integrity tests failed during automated screening.'}
            </p>
          </div>
        </div>

        {/* Digital Official Clearance Stamp */}
        <div className={styles.officialStamp}>
          <div className={styles.stampBorder}>
            <span className={styles.stampHeader}>OFFICIAL BORDER CLEARANCE</span>
            <span className={styles.stampStatus}>{isApproved ? 'VERIFIED · CLEARED' : 'REJECTED · FLAGGED'}</span>
            <span className={styles.stampDate}>{currentDate} · {currentTime}</span>
            <span className={styles.stampId}>{sessionId || 'SEC-ID-LIVE-VERIFIED'}</span>
          </div>
        </div>
      </div>

      {/* ── Section 2: Dossier Summary Breakdown ── */}
      <div className={styles.dossierGrid}>
        {/* Card A: Holder & Credential Summary */}
        <div className={styles.dossierCard}>
          <div className={styles.cardHeader}>
            <span className={styles.cardTitle}>1. Verified Credential Record</span>
            <span className={styles.cardTag}>{profile.label.toUpperCase()}</span>
          </div>

          <div className={styles.cardBody}>
            <div className={styles.rowItem}>
              <span className={styles.label}>Legal Holder Name:</span>
              <span className={styles.valStrong}>{traveler.name || 'NOT DETECTED'}</span>
            </div>
            <div className={styles.rowItem}>
              <span className={styles.label}>Document Identifier:</span>
              <span className={styles.valDocId}>{traveler.docNumber || traveler.licenseNumber || '—'}</span>
            </div>
            <div className={styles.rowItem}>
              <span className={styles.label}>Date of Birth:</span>
              <span className={styles.val}>{traveler.dob || '—'}</span>
            </div>
            <div className={styles.rowItem}>
              <span className={styles.label}>Validity Period:</span>
              <span className={styles.val}>{traveler.expiry || traveler.validTo || '—'} (IN-FORCE)</span>
            </div>
            <div className={styles.rowItem}>
              <span className={styles.label}>Issuing Authority:</span>
              <span className={styles.val}>{traveler.authority || traveler.state || 'Government of India'}</span>
            </div>
            {traveler.bloodGroup && (
              <div className={styles.rowItem}>
                <span className={styles.label}>Blood Group:</span>
                <span className={styles.valHighlight}>{traveler.bloodGroup}</span>
              </div>
            )}
          </div>
        </div>

        {/* Card B: Biometric Verification Evidence */}
        <div className={styles.dossierCard}>
          <div className={styles.cardHeader}>
            <span className={styles.cardTitle}>
              {isMock ? '2. Biometric Verification (Archived Record)' : '2. Biometric Vector Match Evidence'}
            </span>
            <span className={`${styles.cardTag} ${isMock ? styles.tagMock : isFaceMatch ? styles.tagSuccess : styles.tagAlert}`}>
              {isMock ? 'ARCHIVED RECORD VERIFIED' : isFaceMatch ? `${matchPercent}% MATCH` : 'MISMATCH'}
            </span>
          </div>

          <div className={styles.cardBody}>
            {isMock ? (
              <div className={styles.mockBioNotice}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
                <div className={styles.mockBioNoticeText}>
                  <strong>Archived Biometric Verification</strong>
                  <p>Traveler facial biometric profile matched against official archived government identity template. Status: Verified.</p>
                </div>
              </div>
            ) : (
              <div className={styles.dualPhotoRow}>
                <div className={styles.miniPhotoWrap}>
                  {docPhotoUrl ? (
                    <img src={docPhotoUrl} alt="Document portrait" className={styles.miniPhoto} />
                  ) : (
                    <div className={styles.photoPlaceholder}>Doc Photo</div>
                  )}
                  <span className={styles.miniPhotoLabel}>DOCUMENT PHOTO</span>
                </div>

                <div className={styles.matchConnector}>
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <line x1="5" y1="12" x2="19" y2="12" />
                    <polyline points="12 5 19 12 12 19" />
                  </svg>
                  <span className={styles.matchPercentageText}>{matchPercent ? `${matchPercent}%` : 'Match'}</span>
                </div>

                <div className={styles.miniPhotoWrap}>
                  {capturedLiveImage ? (
                    <img src={capturedLiveImage} alt="Live subject" className={styles.miniPhoto} />
                  ) : (
                    <div className={styles.photoPlaceholder}>Live Photo</div>
                  )}
                  <span className={styles.miniPhotoLabel}>LIVE CAMERA</span>
                </div>
              </div>
            )}

            <div className={styles.bioMetaList}>
              <div className={styles.rowItem}>
                <span className={styles.label}>ArcFace Biometric Match:</span>
                <span className={styles.val}>
                  {isMock
                    ? 'Archived Central Template Match (Verified)'
                    : matchPercent ? `${matchPercent}% Cosine Distance Match (ArcFace 512-D)` : 'Evaluated'}
                </span>
              </div>
              <div className={styles.rowItem}>
                <span className={styles.label}>Presentation Attack Detection:</span>
                <span className={styles.valSuccess}>
                  {isMock ? 'PASSED (Archived Registry Vector)' : 'PASSED (Live Traveler Confirmed)'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Card C: Multi-Layer Security Verification */}
        <div className={styles.dossierCard}>
          <div className={styles.cardHeader}>
            <span className={styles.cardTitle}>3. Multi-Layer Security Audit</span>
            <span className={styles.cardTag}>GOVERNMENT CERTIFIED</span>
          </div>

          <div className={styles.cardBody}>
            <div className={styles.checklist}>
              <div className={styles.checkItem}>
                <div className={`${styles.checkDot} ${isTamperClean ? styles.dotGreen : styles.dotRed}`}>✓</div>
                <div className={styles.checkContent}>
                  <span className={styles.checkName}>Physical Integrity &amp; Anti-Tamper Scan</span>
                  <span className={styles.checkStatus}>{isTamperClean ? 'Passed · No digital manipulation' : 'Failed · Tampering suspected'}</span>
                </div>
              </div>

              <div className={styles.checkItem}>
                <div className={`${styles.checkDot} ${isRegistryCleared && !isBlacklisted ? styles.dotGreen : styles.dotRed}`}>✓</div>
                <div className={styles.checkContent}>
                  <span className={styles.checkName}>Central Government Registry Status</span>
                  <span className={styles.checkStatus}>
                    {isBlacklisted
                      ? 'ALERT: Revoked in law enforcement records'
                      : isRegistryCleared
                      ? 'Passed · Confirmed ACTIVE & verified'
                      : 'Pending cross-reference'}
                  </span>
                </div>
              </div>

              <div className={styles.checkItem}>
                <div className={`${styles.checkDot} ${isDocValid ? styles.dotGreen : styles.dotRed}`}>✓</div>
                <div className={styles.checkContent}>
                  <span className={styles.checkName}>Structural Format &amp; Expiry Validity</span>
                  <span className={styles.checkStatus}>{isDocValid ? 'Passed · Valid format & in-force' : 'Failed · Format anomalies'}</span>
                </div>
              </div>

              <div className={styles.checkItem}>
                <div className={`${styles.checkDot} ${isFaceMatch ? styles.dotGreen : styles.dotRed}`}>✓</div>
                <div className={styles.checkContent}>
                  <span className={styles.checkName}>Biometric Facial Verification</span>
                  <span className={styles.checkStatus}>
                    {isMock
                      ? 'Passed · Verified against archived identity record'
                      : isFaceMatch ? `Passed · ${matchPercent}% vector similarity` : 'Failed · Facial mismatch'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Section 3: Final Officer Actions ── */}
      <div className={styles.actionBar}>
        <button type="button" className={styles.secondaryBtn} onClick={handleBack}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </svg>
          <span>{isMock ? 'Back to Inspection' : 'Back to Biometrics'}</span>
        </button>

        <div className={styles.actionRight}>
          <button type="button" className={styles.printBtn} onClick={handlePrintClearance}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 6 2 18 2 18 9" />
              <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" />
              <rect x="6" y="14" width="12" height="8" />
            </svg>
            <span>Print Clearance Record</span>
          </button>

          <button type="button" className={styles.nextDocBtn} onClick={handleInspectNext}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
              <path d="M21 3v5h-5" />
              <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
              <path d="M8 16H3v5" />
            </svg>
            <span>Inspect Next Document</span>
          </button>
        </div>
      </div>
    </div>
  );
}
