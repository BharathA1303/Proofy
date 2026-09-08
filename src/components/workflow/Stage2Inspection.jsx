/**
 * Stage2Inspection.jsx
 *
 * Stage 2: Executive Officer Inspection & Verification Dossier.
 * Built specifically for border/police/transport inspection officers:
 *   - High-contrast, clean identity profile (Name, Document #, DOB, Expiry, Authority).
 *   - Clear executive status badges (Document Authenticity, Registry Clearance, Format Validity).
 *   - Plain-language officer directives without distracting technical jargon.
 *   - Collapsible "Technical Audit & Forensic Logs" for audit engineers.
 */
import { useVerification } from '../../state/verification/useVerification.js';
import { DOCUMENT_PROFILES, DOCUMENT_TYPES } from '../../config/documentProfiles.js';
import styles from './Stage2Inspection.module.css';

export default function Stage2Inspection() {
  const { session, actions } = useVerification();

  const profile = DOCUMENT_PROFILES[session.documentType] || DOCUMENT_PROFILES[DOCUMENT_TYPES.PASSPORT];
  const traveler = session.traveler || {};
  const checks = session.checks || {};
  const forensicDetail = session.forensicDetail || {};
  const registryDetail = session.registryDetail || {};
  const result = session.result || {};

  // Status determinations
  const isDocValid = checks.documentValidation === 'passed';
  const isTamperClean = checks.tamperingDetection !== 'failed';
  const regStatus = registryDetail?.registry?.status || '';
  const isRegistryCleared = regStatus === 'MATCHED' || checks.registryVerification === 'passed';
  const isBlacklisted = regStatus === 'REVOKED' || regStatus === 'SUSPENDED' || regStatus === 'BLACKLISTED';

  // Overall officer tier
  const isCleanGenuine = isDocValid && isTamperClean && isRegistryCleared && !isBlacklisted;
  const hasCriticalWarning = isBlacklisted || checks.tamperingDetection === 'failed' || checks.documentValidation === 'failed';

  // Document photo preview
  const docFile = session.file;
  const docPreviewUrl = (docFile && docFile instanceof File) ? URL.createObjectURL(docFile) : null;

  const isMock = Boolean(session.isMockVector);

  function handleProceedNext() {
    if (isMock) {
      // Archived digital registry dossiers proceed directly to Stage 4 clearance
      actions.setWorkflowStage(4);
    } else {
      // Physical credentials require live camera biometric face verification
      actions.setWorkflowStage(3);
    }
  }

  function handleBackToIntake() {
    actions.setWorkflowStage(1);
  }

  return (
    <div className={styles.stageContainer}>
      {/* ── Header Ribbon ── */}
      <div className={styles.headerBlock}>
        <div className={styles.badgeRow}>
          <span className={styles.stageBadge}>STAGE 2 OF 4</span>
          <span className={styles.stageTitleTag}>OFFICER INSPECTION REPORT</span>
        </div>
        <div className={styles.titleRow}>
          <div>
            <h2 className={styles.mainTitle}>Document &amp; Official Records Report</h2>
            <p className={styles.mainSubtitle}>
              Document details and automated security verification results for {profile.label}.
            </p>
          </div>

          <div className={`${styles.officerStatusPill} ${isCleanGenuine ? styles.pillApproved : hasCriticalWarning ? styles.pillAlert : styles.pillReview}`}>
            <span className={styles.statusDot} />
            <span>
              {isCleanGenuine
                ? 'DOCUMENT VERIFIED AUTHENTIC'
                : isBlacklisted
                ? 'CRITICAL: WATCHLIST ALERT'
                : !isTamperClean
                ? 'DEFECTIVE / ALTERATION DETECTED'
                : regStatus === 'NOT_FOUND' || !isRegistryCleared
                ? 'UNREGISTERED / NOT IN DATABASE'
                : hasCriticalWarning
                ? 'DEFECTIVE / COUNTERFEIT DETECTED'
                : 'OFFICER REVIEW ADVISED'}
            </span>
          </div>
        </div>
      </div>

      {/* ── Section 1: Executive Identity Profile Card ── */}
      <div className={styles.profileCard}>
        <div className={styles.profileHeader}>
          <div className={styles.profileHeaderLeft}>
            <span className={styles.profileHeaderTitle}>Extracted Identity Profile</span>
            <span className={styles.docTypeTag}>{profile.label.toUpperCase()}</span>
          </div>
          <span className={styles.sourceTag}>Automated Document Extraction</span>
        </div>

        <div className={styles.profileBody}>
          {/* Document Photo / Scan Preview */}
          <div className={styles.photoContainer}>
            {docPreviewUrl ? (
              <img src={docPreviewUrl} alt="Document photograph scan" className={styles.holderDocPhoto} />
            ) : (
              <div className={styles.photoPlaceholder}>
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
                <span>Document Photo</span>
              </div>
            )}
            <span className={styles.photoLabel}>PHYSICAL DOCUMENT</span>
          </div>

          {/* Extracted Fields Grid */}
          <div className={styles.fieldsContainer}>
            <div className={styles.primaryIdentityRow}>
              <div className={styles.fieldItem}>
                <span className={styles.fieldLabel}>FULL NAME</span>
                <span className={styles.fieldValueName}>{traveler.name || 'NOT DETECTED'}</span>
              </div>
              <div className={styles.fieldItem}>
                <span className={styles.fieldLabel}>DOCUMENT NUMBER</span>
                <span className={styles.fieldValueDocNum}>{traveler.docNumber || traveler.licenseNumber || traveler.identityNumber || '—'}</span>
              </div>
            </div>

            <div className={styles.secondaryFieldsGrid}>
              <div className={styles.fieldItem}>
                <span className={styles.fieldLabel}>DATE OF BIRTH</span>
                <span className={styles.fieldValue}>{traveler.dob || '—'}</span>
              </div>
              <div className={styles.fieldItem}>
                <span className={styles.fieldLabel}>EXPIRY DATE</span>
                <span className={styles.fieldValueExpiry}>
                  {traveler.expiry || traveler.validTo || '—'}
                  {traveler.expiry && <span className={styles.inForcePill}>VALID</span>}
                </span>
              </div>
              <div className={styles.fieldItem}>
                <span className={styles.fieldLabel}>ISSUE DATE</span>
                <span className={styles.fieldValue}>{traveler.issuedDate || traveler.issueDate || '—'}</span>
              </div>
              <div className={styles.fieldItem}>
                <span className={styles.fieldLabel}>ISSUING AUTHORITY</span>
                <span className={styles.fieldValue}>{traveler.authority || traveler.issuingAuthority || '—'}</span>
              </div>
              {traveler.nationality && (
                <div className={styles.fieldItem}>
                  <span className={styles.fieldLabel}>NATIONALITY</span>
                  <span className={styles.fieldValue}>{traveler.nationality}</span>
                </div>
              )}
              {traveler.gender && (
                <div className={styles.fieldItem}>
                  <span className={styles.fieldLabel}>GENDER</span>
                  <span className={styles.fieldValue}>{traveler.gender}</span>
                </div>
              )}
              {traveler.bloodGroup && (
                <div className={styles.fieldItem}>
                  <span className={styles.fieldLabel}>BLOOD GROUP</span>
                  <span className={styles.fieldValueHighlight}>{traveler.bloodGroup}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── Section 2: Officer Security Verification Badges ── */}
      <div className={styles.securityGrid}>
        {/* Check 1: Document Authenticity & Physical Integrity */}
        <div className={`${styles.securityCard} ${isTamperClean ? styles.secPassed : styles.secFailed}`}>
          <div className={styles.secTop}>
            <div className={styles.secIcon}>
              {isTamperClean ? (
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                  <path d="m9 12 2 2 4-4" />
                </svg>
              ) : (
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
              )}
            </div>
            <span className={styles.secStatusTag}>
              {isTamperClean ? 'SUBSTRATE INTACT' : 'TAMPERING SUSPECTED'}
            </span>
          </div>
          <h4 className={styles.secTitle}>Document Authenticity</h4>
          <p className={styles.secDesc}>
            {isTamperClean
              ? 'No structural tampering, photo alterations, or digital splicing detected on this document image.'
              : 'Suspicious photo modifications or digital alterations detected on this document.'}
          </p>
        </div>

        {/* Check 2: Central Government Registry Cross-Check */}
        <div className={`${styles.securityCard} ${isRegistryCleared && !isBlacklisted ? styles.secPassed : isBlacklisted ? styles.secAlert : styles.secReview}`}>
          <div className={styles.secTop}>
            <div className={styles.secIcon}>
              {isRegistryCleared && !isBlacklisted ? (
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                  <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                  <polyline points="9 11 11 13 15 9" />
                </svg>
              ) : (
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
                  <line x1="12" y1="9" x2="12" y2="13" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
              )}
            </div>
            <span className={styles.secStatusTag}>
              {isBlacklisted
                ? 'WATCHLIST ALERT'
                : isRegistryCleared
                ? 'CLEARED · ACTIVE'
                : regStatus === 'NOT_FOUND'
                ? 'NOT REGISTERED IN DATABASE'
                : 'RECORDS UNVERIFIED'}
            </span>
          </div>
          <h4 className={styles.secTitle}>Government Records Status</h4>
          <p className={styles.secDesc}>
            {isBlacklisted
              ? (registryDetail?.evidence?.find((e) => e.severity === 'critical')?.description ||
                 registryDetail?.registry?.message ||
                 'CRITICAL ALERT: This document number is officially REVOKED/SUSPENDED on national security watchlists.')
              : isRegistryCleared
              ? `Document number is verified ACTIVE and registered to ${traveler.name || 'holder'} in official records.`
              : regStatus === 'NOT_FOUND'
              ? `Document number ${traveler.docNumber || traveler.licenseNumber || traveler.identityNumber || 'extracted'} is NOT registered in official Government records. Unregistered credential.`
              : 'Central records cross-reference returned cautionary flags or pending status.'}
          </p>
        </div>

        {/* Check 3: Format & Validity */}
        <div className={`${styles.securityCard} ${isDocValid ? styles.secPassed : styles.secFailed}`}>
          <div className={styles.secTop}>
            <div className={styles.secIcon}>
              {isDocValid ? (
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                  <line x1="16" y1="2" x2="16" y2="6" />
                  <line x1="8" y1="2" x2="8" y2="6" />
                  <line x1="3" y1="10" x2="21" y2="10" />
                </svg>
              ) : (
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="15" y1="9" x2="9" y2="15" />
                  <line x1="9" y1="9" x2="15" y2="15" />
                </svg>
              )}
            </div>
            <span className={styles.secStatusTag}>
              {isDocValid ? 'VALID & ACTIVE' : 'FORMAT ISSUE DETECTED'}
            </span>
          </div>
          <h4 className={styles.secTitle}>Document Validity &amp; Dates</h4>
          <p className={styles.secDesc}>
            {isDocValid
              ? 'Validity dates and document structure verified. All required fields adhere to official standards.'
              : (session.validationDetail?.errors?.length
                  ? `Format / validation issues: ${session.validationDetail.errors.join('; ')}`
                  : 'Issues detected: invalid dates, incorrect format, or missing required fields.')}
          </p>
        </div>
      </div>

      {/* ── Section 3: Officer Directive Callout ── */}
      <div className={`${styles.directiveBox} ${isCleanGenuine ? styles.dirApproved : styles.dirAlert}`}>
        <div className={styles.dirIcon}>
          {isCleanGenuine ? (
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          ) : (
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
              <line x1="12" y1="9" x2="12" y2="13" />
            </svg>
          )}
        </div>
        <div className={styles.dirText}>
          <h4 className={styles.dirTitle}>
            {isCleanGenuine
              ? (isMock ? 'Officer Directive: Document Validated — Official Records Matched' : 'Officer Directive: Document Validated — Live Face Match Required')
              : isBlacklisted
              ? 'Officer Directive: WATCHLIST ALERT — Flagged on Law Enforcement Database'
              : !isTamperClean
              ? 'Officer Directive: Counterfeit / Altered Document Suspected'
              : regStatus === 'NOT_FOUND' || !isRegistryCleared
              ? 'Officer Directive: Unregistered Document — Not Found in Government Registry'
              : !isDocValid
              ? 'Officer Directive: Document Format / Validity Defect'
              : 'Officer Directive: Secondary Inspection Advised'}
          </h4>
          <p className={styles.dirDesc}>
            {isCleanGenuine
              ? (isMock
                  ? 'Document format and official records verified. Identity confirmed on file. Proceed to Stage 4 for final clearance.'
                  : `Authentic document verified for ${traveler.name || 'holder'}. Proceed to Stage 3 for live camera face photo matching.`)
              : isBlacklisted
              ? 'This document is registered on a law enforcement watchlist. Do not clear traveler without supervisor authorization.'
              : !isTamperClean
              ? 'Digital alterations, photo replacement, or substrate tampering marks were detected during automated inspection.'
              : regStatus === 'NOT_FOUND' || !isRegistryCleared
              ? `The document number (${traveler.docNumber || traveler.licenseNumber || traveler.identityNumber || 'extracted'}) is NOT found in official Government of India records. It cannot be cleared as a legitimate document.`
              : !isDocValid
              ? (session.validationDetail?.errors?.[0] || 'Required document fields or validity dates fail official government specifications.')
              : 'Discrepancies identified during automated inspection. Refer traveler for secondary verification.'}
          </p>
        </div>
      </div>

      {/* ── Section 5: Stage Navigation Actions ── */}
      <div className={styles.actionBar}>
        <button
          type="button"
          className={styles.backBtn}
          onClick={handleBackToIntake}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </svg>
          <span>Back to Document Intake</span>
        </button>

        <button
          type="button"
          className={styles.proceedBtn}
          onClick={handleProceedNext}
        >
          <span>
            {isMock
              ? 'Proceed to Stage 4: Final Clearance Decision'
              : 'Proceed to Stage 3: Live Face Verification'}
          </span>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <line x1="5" y1="12" x2="19" y2="12" />
            <polyline points="12 5 19 12 12 19" />
          </svg>
        </button>
      </div>
    </div>
  );
}
