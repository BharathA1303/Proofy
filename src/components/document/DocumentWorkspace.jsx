/**
 * DocumentWorkspace.jsx
 *
 * Unified Document Verification Workbench.
 * Consolidates credential intake, extracted identity, automated inspection,
 * biometrics, and audit forensics into a cohesive modern workspace.
 */
import { useVerification } from '../../state/verification/useVerification.js';
import { DOCUMENT_PROFILES, DOCUMENT_TYPES } from '../../config/documentProfiles.js';
import { SESSION_STATUS } from '../../state/verification/initialState.js';
import UploadPanel from '../upload/UploadPanel.jsx';
import TravelerInformation from '../traveler/TravelerInformation.jsx';
import VerificationResult from '../verification/VerificationResult.jsx';
import VerificationChecks from '../verification/VerificationChecks.jsx';
import BiometricStatus from '../biometric/BiometricStatus.jsx';
import MilestoneStepper from '../milestone/MilestoneStepper.jsx';
import styles from './DocumentWorkspace.module.css';

function getTechnicalSpec(docType) {
  switch (docType) {
    case DOCUMENT_TYPES.PASSPORT:       return 'ICAO DOC 9303 · PART 4 (TD3)';
    case DOCUMENT_TYPES.VISA:           return 'ICAO DOC 9303 · PART 7 (MRV)';
    case DOCUMENT_TYPES.DRIVING_LICENSE:return 'ISO/IEC 18013-1 STANDARD';
    case DOCUMENT_TYPES.NATIONAL_ID:    return 'ICAO DOC 9303 · PART 5 (TD1)';
    case DOCUMENT_TYPES.BORDER_PERMIT:  return 'UN ECE TRANSIT PROTOCOL';
    default: return 'SECURITY STANDARD';
  }
}

export default function DocumentWorkspace() {
  const { session, actions } = useVerification();
  const profile = DOCUMENT_PROFILES[session.documentType];
  const technicalSpec = getTechnicalSpec(session.documentType);

  const isStandby = session.status === SESSION_STATUS.STANDBY;
  const statusLabel = isStandby ? 'Awaiting Document' : session.status.replace(/_/g, ' ');

  return (
    <div
      className={styles.workspace}
      id={`tabpanel-${session.documentType}`}
      role="tabpanel"
      aria-labelledby={`tab-${session.documentType}`}
    >
      {/* Document type context ribbon */}
      <div className={styles.contextRibbon}>
        <div className={styles.ribbonLeft}>
          <div className={styles.profileIndicator}>
            <span className={styles.docTypeLabel}>{profile?.label ?? 'Document'}</span>
            <span className={styles.techSpec}>{technicalSpec}</span>
          </div>

          <div className={`${styles.statusPill} ${styles[session.status] || ''}`}>
            <span className={styles.statusDot} aria-hidden="true" />
            <span className={styles.statusText}>{statusLabel}</span>
          </div>
        </div>

        <div className={styles.ribbonRight}>
          <button
            className={styles.resetBtn}
            onClick={() => actions.resetSession()}
            type="button"
            title="Reset active verification session"
            aria-label="Reset active verification session"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
              <path d="M21 3v5h-5" />
              <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
              <path d="M8 16H3v5" />
            </svg>
            <span>Reset Terminal</span>
          </button>
        </div>
      </div>

      {/* Sequential Milestone Pipeline Stepper */}
      <MilestoneStepper />

      {/* Unified Master Grid: Consolidated Process & Components */}
      <div className={styles.workbenchGrid}>
        {/* ── Left Master Card: Document Credential & Traveler Identity ── */}
        <section className={styles.masterCard} aria-labelledby="card-title-document">
          <header className={styles.cardHeader}>
            <div className={styles.headerIcon}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="3" y="4" width="18" height="16" rx="2" />
                <line x1="7" y1="8" x2="17" y2="8" />
                <line x1="7" y1="12" x2="13" y2="12" />
              </svg>
            </div>
            <div>
              <h2 id="card-title-document" className={styles.cardTitle}>Credential & Identity Records</h2>
              <p className={styles.cardSubtitle}>Ingestion, OCR text extraction, and verified traveler identity</p>
            </div>
          </header>

          <div className={styles.cardContent}>
            <UploadPanel />
            <hr className={styles.divider} />
            <TravelerInformation />
          </div>
        </section>

        {/* ── Right Master Card: Automated Verification & Telemetry Suite ── */}
        <section className={styles.masterCard} aria-labelledby="card-title-verification">
          <header className={styles.cardHeader}>
            <div className={styles.headerIcon}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                <path d="m9 12 2 2 4-4" />
              </svg>
            </div>
            <div>
              <h2 id="card-title-verification" className={styles.cardTitle}>Automated Inspection Suite</h2>
              <p className={styles.cardSubtitle}>Pipeline security checks, biometric telemetry, and forensic audit trail</p>
            </div>
          </header>

          <div className={styles.cardContent}>
            <VerificationResult />
            <hr className={styles.divider} />
            <VerificationChecks />
            <BiometricStatus />
          </div>
        </section>
      </div>
    </div>
  );
}
