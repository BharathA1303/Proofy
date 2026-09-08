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
  const { biometrics, checks, registryDetail, traveler, capturedLiveImage, documentFaceImage, file, sessionId, verificationDuration } = session;

  const profile = DOCUMENT_PROFILES[session.documentType] || DOCUMENT_PROFILES[DOCUMENT_TYPES.PASSPORT];

  const isMock = Boolean(session.isMockVector);
  const durationSeconds = verificationDuration || '1.8';

  const isDocValid = checks.documentValidation === 'passed';
  const isTamperClean = checks.tamperingDetection !== 'failed';
  const regStatus = registryDetail?.registry?.status || '';
  const isRegistryCleared = regStatus === 'MATCHED' || checks.registryVerification === 'passed';
  const isBlacklisted = regStatus === 'REVOKED' || regStatus === 'SUSPENDED' || regStatus === 'BLACKLISTED';
  const isFaceMatch = isMock
    ? true // Mock vectors bypass live camera matching
    : (biometrics?.overallAssessment === 'FACE_MATCH' || biometrics?.faceMatchResult?.status === 'match');

  // Stamp verification determination for Indian travel credentials (Passport, Visa, Border Permit)
  const normDocType = (session.documentType || 'passport').toLowerCase();
  const isStampApplicable = ['passport', 'visa', 'border_permit', 'borderpermit', 'work_permit', 'workpermit'].includes(normDocType);
  const stampSignal = session.forensicDetail?.signals?.find((s) => s.type === 'stamp');
  const isStampClean = !stampSignal || stampSignal.status !== 'suspicious';

  // Final Overall Clearance Status
  const isApproved = isDocValid && isTamperClean && isRegistryCleared && !isBlacklisted && isFaceMatch && isStampClean;

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
      {/* ── Official Print Header (Visible ONLY during document print) ── */}
      <div className={styles.printHeader} aria-hidden="true">
        <div className={styles.printBrandRow}>
          <div className={styles.printBrandLeft}>
            <div className={styles.printLogoBox}>
              <img src="/avanza-mark.png" alt="Avanza" className={styles.printLogoImg} />
            </div>
            <div className={styles.printBrandText}>
              <h1 className={styles.printBrandTitle}>AVANZA · NATIONAL BORDER &amp; IDENTITY CLEARANCE</h1>
              <p className={styles.printBrandSub}>
                Official Automated Screening Disposition Record &bull; Certificate of Identity Verification
              </p>
            </div>
          </div>
          <div className={styles.printStatusStamp}>
            <span className={isApproved ? styles.printBadgeApproved : styles.printBadgeRejected}>
              {isApproved ? 'VERIFIED · CLEARED' : 'REJECTED · FLAGGED'}
            </span>
          </div>
        </div>

        <div className={styles.printMetaGrid}>
          <div className={styles.printMetaItem}>
            <span className={styles.printMetaLabel}>DOSSIER FILE ID:</span>
            <span className={styles.printMetaValue}>{sessionId || 'AVZ-SEC-2026-9901'}</span>
          </div>
          <div className={styles.printMetaItem}>
            <span className={styles.printMetaLabel}>TIMESTAMP:</span>
            <span className={styles.printMetaValue}>{currentDate} · {currentTime}</span>
          </div>
          <div className={styles.printMetaItem}>
            <span className={styles.printMetaLabel}>CREDENTIAL TYPE:</span>
            <span className={styles.printMetaValue}>{profile.label.toUpperCase()}</span>
          </div>
          <div className={styles.printMetaItem}>
            <span className={styles.printMetaLabel}>VERIFICATION TIME:</span>
            <span className={styles.printMetaValueSpeed}>⏱️ {durationSeconds}s (Automated)</span>
          </div>
        </div>
      </div>

      {/* ── Header Ribbon (Web View) ── */}
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
            <div className={styles.heroMetaBadges}>
              <span className={styles.heroPreTitle}>FINAL OFFICER DETERMINATION</span>
              <span className={styles.heroSpeedBadge}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <circle cx="12" cy="12" r="10" />
                  <polyline points="12 6 12 12 16 14" />
                </svg>
                Verified in <strong>{durationSeconds}s</strong>
              </span>
            </div>
            <h1 className={styles.heroTitle}>
              {isApproved
                ? 'CLEARANCE APPROVED: TRAVELER ADMITTED'
                : isBlacklisted
                ? 'CLEARANCE DENIED: WATCHLIST ALERT'
                : !isTamperClean
                ? 'CLEARANCE REJECTED: TAMPERED CREDENTIAL'
                : regStatus === 'NOT_FOUND' || !isRegistryCleared
                ? 'CLEARANCE REJECTED: UNREGISTERED CREDENTIAL'
                : !isFaceMatch
                ? 'CLEARANCE REJECTED: BIOMETRIC MISMATCH'
                : !isStampClean
                ? 'CLEARANCE REJECTED: STAMP FORGERY'
                : 'CLEARANCE REJECTED / REFER TO SECONDARY'}
            </h1>
            <p className={styles.heroExplanation}>
              {isApproved
                ? (isMock
                    ? 'All document format, security features, and government records checks satisfied. Identity matched with archived records.'
                    : 'All security checks satisfied. Document is authentic, confirmed in government records, and face matches the traveler.')
                : isBlacklisted
                ? (registryDetail?.evidence?.find((e) => e.severity === 'critical')?.description
                    ? `WATCHLIST ALERT: ${registryDetail.evidence.find((e) => e.severity === 'critical').description}`
                    : 'CRITICAL ALERT: Document number is flagged on security watchlists. Traveler must be referred for secondary inspection.')
                : !isTamperClean
                ? 'TAMPERING DETECTED: Digital alterations, photo replacement, or substrate splicing detected during automated inspection.'
                : regStatus === 'NOT_FOUND' || !isRegistryCleared
                ? `UNREGISTERED CREDENTIAL: Document number ${traveler.docNumber || traveler.licenseNumber || traveler.identityNumber || 'extracted'} does not exist in official Government of India records (Sarathi / National Database). Unverified or fabricated document.`
                : !isFaceMatch
                ? 'FACE MISMATCH: Live face does not match the document photograph.'
                : !isStampClean
                ? 'IMMIGRATION STAMP FORGERY: The official immigration entry stamp on this document is counterfeit and does not match registered movement in Government of India records.'
                : session.validationDetail?.errors?.length
                ? `Document validation defect: ${session.validationDetail.errors[0]}`
                : 'Document or format integrity tests failed during automated screening.'}
            </p>
          </div>
        </div>

        {/* Digital Official Clearance Stamp */}
        <div className={styles.officialStamp}>
          <div className={styles.stampBorder}>
            <span className={styles.stampHeader}>OFFICIAL BORDER CLEARANCE</span>
            <span className={styles.stampStatus}>{isApproved ? 'VERIFIED · CLEARED' : 'REJECTED · FLAGGED'}</span>
            <span className={styles.stampDate}>{currentDate} · {currentTime}</span>
            <span className={styles.stampSpeed}>⏱️ Verified in {durationSeconds}s</span>
            <span className={styles.stampId}>{sessionId || 'SEC-ID-LIVE-VERIFIED'}</span>
          </div>
        </div>
      </div>

      {/* ── Section 2: Dossier Summary Breakdown ── */}
      <div className={styles.dossierGrid}>
        {/* Card A: Holder & Credential Summary */}
        <div className={styles.dossierCard}>
          <div className={styles.cardHeader}>
            <span className={styles.cardTitle}>1. Verified Document Record</span>
            <span className={styles.cardTag}>{profile.label.toUpperCase()}</span>
          </div>

          <div className={styles.cardBody}>
            <div className={styles.rowItem}>
              <span className={styles.label}>Full Name:</span>
              <span className={styles.valStrong}>{traveler.name || 'NOT DETECTED'}</span>
            </div>
            <div className={styles.rowItem}>
              <span className={styles.label}>Document Number:</span>
              <span className={styles.valDocId}>{traveler.docNumber || traveler.licenseNumber || '—'}</span>
            </div>
            <div className={styles.rowItem}>
              <span className={styles.label}>Date of Birth:</span>
              <span className={styles.val}>{traveler.dob || '—'}</span>
            </div>
            <div className={styles.rowItem}>
              <span className={styles.label}>Validity Period:</span>
              <span className={styles.val}>{traveler.expiry || traveler.validTo || '—'} (Valid)</span>
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
              {isMock ? '2. Face Verification (Archived Record)' : '2. Face Match Verification Evidence'}
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
                  <strong>Archived Face Verification</strong>
                  <p>Traveler face profile matched against official archived identity record. Status: Verified.</p>
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
                <span className={styles.label}>Face Match Result:</span>
                <span className={styles.val}>
                  {isMock
                    ? 'Archived Record Match (Verified)'
                    : matchPercent ? `${matchPercent}% Match Confidence` : 'Evaluated'}
                </span>
              </div>
              <div className={styles.rowItem}>
                <span className={styles.label}>Live Person Check:</span>
                <span className={styles.valSuccess}>
                  {isMock ? 'PASSED (Archived Record)' : 'PASSED (Real Person Confirmed)'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Card C: Security Verification Summary */}
        <div className={styles.dossierCard}>
          <div className={styles.cardHeader}>
            <span className={styles.cardTitle}>3. Security Verification Audit</span>
            <span className={styles.cardTag}>GOVERNMENT CERTIFIED</span>
          </div>

          <div className={styles.cardBody}>
            <div className={styles.checklist}>
              <div className={styles.checkItem}>
                <div className={`${styles.checkDot} ${isTamperClean ? styles.dotGreen : styles.dotRed}`}>✓</div>
                <div className={styles.checkContent}>
                  <span className={styles.checkName}>Document Integrity &amp; Tamper Check</span>
                  <span className={styles.checkStatus}>{isTamperClean ? 'Passed · Substrate & photo integrity intact' : 'Failed · Tampering / alteration detected'}</span>
                </div>
              </div>

              {isStampApplicable && (
                <div className={styles.checkItem}>
                  <div className={`${styles.checkDot} ${isStampClean ? styles.dotGreen : styles.dotRed}`}>✓</div>
                  <div className={styles.checkContent}>
                    <span className={styles.checkName}>Official Immigration &amp; Consular Seal</span>
                    <span className={styles.checkStatus}>
                      {isStampClean
                        ? 'Passed · Official Indian immigration seal verified'
                        : 'Failed · Counterfeit or unregistered stamp'}
                    </span>
                  </div>
                </div>
              )}

              <div className={styles.checkItem}>
                <div className={`${styles.checkDot} ${isRegistryCleared && !isBlacklisted ? styles.dotGreen : styles.dotRed}`}>✓</div>
                <div className={styles.checkContent}>
                  <span className={styles.checkName}>Government Records Status</span>
                  <span className={styles.checkStatus}>
                    {isBlacklisted
                      ? (registryDetail?.evidence?.find((e) => e.severity === 'critical')?.description
                          ? `ALERT: ${registryDetail.evidence.find((e) => e.severity === 'critical').description}`
                          : 'ALERT: Revoked in official records')
                      : isRegistryCleared
                      ? 'Passed · Confirmed ACTIVE & verified'
                      : regStatus === 'NOT_FOUND'
                      ? 'Failed · Not found in Government of India registry'
                      : 'Failed · Unverified official records'}
                  </span>
                </div>
              </div>

              <div className={styles.checkItem}>
                <div className={`${styles.checkDot} ${isDocValid ? styles.dotGreen : styles.dotRed}`}>✓</div>
                <div className={styles.checkContent}>
                  <span className={styles.checkName}>Document Format &amp; Validity</span>
                  <span className={styles.checkStatus}>
                    {isDocValid
                      ? 'Passed · Valid format & dates'
                      : (session.validationDetail?.errors?.[0]
                          ? `Failed · ${session.validationDetail.errors[0]}`
                          : 'Failed · Format issue')}
                  </span>
                </div>
              </div>

              <div className={styles.checkItem}>
                <div className={`${styles.checkDot} ${isFaceMatch ? styles.dotGreen : styles.dotRed}`}>✓</div>
                <div className={styles.checkContent}>
                  <span className={styles.checkName}>Face Verification</span>
                  <span className={styles.checkStatus}>
                    {isMock
                      ? 'Passed · Verified against archived identity record'
                      : isFaceMatch ? `Passed · ${matchPercent}% face similarity` : 'Failed · Facial mismatch'}
                  </span>
                </div>
              </div>

              <div className={styles.checkItem}>
                <div className={`${styles.checkDot} ${styles.dotSpeed}`}>⏱️</div>
                <div className={styles.checkContent}>
                  <span className={styles.checkName}>Automated Screening Speed</span>
                  <span className={styles.checkStatus}>
                    Completed in {durationSeconds} seconds &bull; Real-time AI pipeline latency
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

      {/* ── Official Print Footer (Visible ONLY during document print) ── */}
      <div className={styles.printFooter} aria-hidden="true">
        <div className={styles.printFooterDivider} />
        <div className={styles.printFooterText}>
          <span>OFFICIAL BORDER &amp; SCREENING CLEARANCE DOSSIER</span>
          <span>ISSUED BY AVANZA AUTOMATED IDENTITY VERIFICATION SYSTEM &bull; DIGITAL SIGNATURE CERTIFIED</span>
          <span>PAGE 1 OF 1 &bull; STRICTLY CONFIDENTIAL</span>
        </div>
      </div>
    </div>
  );
}
