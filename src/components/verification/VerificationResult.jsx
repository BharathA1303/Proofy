/**
 * VerificationResult.jsx
 *
 * Displays the top-level verification outcome and threat index.
 *
 * States:
 *   result === null               → "AWAITING DOCUMENT" (standby / processing)
 *   result.decision === 'cleared' → Green cleared banner
 *   result.decision === 'review'  → Amber review banner
 *   result.decision === 'rejected'→ Red rejected banner
 *
 * result is always an object { decision, ... } or null.
 * It is never a bare string.
 *
 * The threat index shows "— / 100" until risk.score is populated.
 */
import { useVerification } from '../../state/verification/useVerification.js';
import { DECISION } from '../../state/verification/initialState.js';
import SectionHeader from '../common/SectionHeader.jsx';
import styles from './VerificationResult.module.css';

const RESULT_CONFIG = {
  [DECISION.CLEARED]: {
    label:     'CLEARED',
    sublabel:  'Document verified. No issues detected.',
    className: styles.cleared,
    ariaLabel: 'Verification result: Cleared',
  },
  [DECISION.REVIEW]: {
    label:     'REQUIRES REVIEW',
    sublabel:  'Manual officer review recommended.',
    className: styles.review,
    ariaLabel: 'Verification result: Requires Review',
  },
  [DECISION.REJECTED]: {
    label:     'REJECTED',
    sublabel:  'Document failed verification. See checks below.',
    className: styles.rejected,
    ariaLabel: 'Verification result: Rejected',
  },
};

export default function VerificationResult() {
  const { session } = useVerification();
  const { result, risk } = session;

  const isStandby    = result === null;
  const resultConfig = result ? RESULT_CONFIG[result.decision] : null;
  const scoreDisplay = risk.score !== null ? `${risk.score} / 100` : '— / 100';

  // Generate 20 segments for the threat meter
  const totalSegments = 20;
  const activeSegments = risk.score !== null ? Math.round((risk.score / 100) * totalSegments) : 0;

  return (
    <div className={styles.section} aria-label="Verification result and threat index">
      <SectionHeader
        title="Verification Decision & Threat Index"
        subtitle="Automated border screening clearance"
        level={3}
      />

      {/* Standby State: Clean Modern Status */}
      {isStandby && (
        <div className={styles.standby} aria-live="polite">
          <div className={styles.standbyIcon} aria-hidden="true">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </div>
          <div className={styles.standbyMeta}>
            <p className={styles.standbyTitle}>Awaiting Credential Verification</p>
            <p className={styles.standbySubtitle}>
              Select or load a document to run automated checks, biometric comparison, and risk scoring.
            </p>
          </div>
        </div>
      )}

      {/* Active result banner */}
      {resultConfig && (
        <div
          className={`${styles.resultBanner} ${resultConfig.className}`}
          role="status"
          aria-label={resultConfig.ariaLabel}
        >
          <div className={styles.bannerHeader}>
            <span className={styles.resultLabel}>{resultConfig.label}</span>
            <span className={styles.decisionPill}>SYSTEM VERDICT</span>
          </div>
          <p className={styles.resultSublabel}>{resultConfig.sublabel}</p>
        </div>
      )}

      {/* Segmented Threat Index Gauge */}
      <div className={styles.threatContainer} aria-label={`Threat Index: ${scoreDisplay}`}>
        <div className={styles.threatHeader}>
          <div className={styles.threatTitleGroup}>
            <span className={styles.threatLabel}>THREAT ASSESSMENT INDEX</span>
            <span className={styles.threatScale}>COMPOSITE RISK ALGORITHM</span>
          </div>
          <span className={`${styles.threatScore} ${risk.score !== null ? styles.scoreActive : ''}`}>
            {scoreDisplay}
          </span>
        </div>

        {/* 20-segment high-tech meter */}
        <div className={styles.meterBar} aria-hidden="true">
          {Array.from({ length: totalSegments }).map((_, i) => {
            const isActive = i < activeSegments;
            let segColorClass = '';
            if (isActive) {
              if (i < 8) segColorClass = styles.segGreen;
              else if (i < 14) segColorClass = styles.segAmber;
              else segColorClass = styles.segRed;
            }

            return (
              <span
                key={i}
                className={`${styles.meterSegment} ${isActive ? styles.segActive : ''} ${segColorClass}`}
              />
            );
          })}
        </div>

        <div className={styles.threatFooter}>
          <span>0 (CLEARED)</span>
          <span>50 (ELEVATED)</span>
          <span>100 (CRITICAL)</span>
        </div>
      </div>
    </div>
  );
}

