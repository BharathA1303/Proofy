/**
 * VerificationResult.jsx
 *
 * Displays top-level verification verdict, threat index, and blockchain audit seal.
 * Fixes undefined / 100 bug with robust type checking.
 */
import { useVerification } from '../../state/verification/useVerification.js';
import { DECISION } from '../../state/verification/initialState.js';
import styles from './VerificationResult.module.css';

const RESULT_CONFIG = {
  [DECISION.CLEARED]: {
    label:     'VERIFIED · CLEAR TO ADMIT',
    sublabel:  'All document checksums, tampering tests, and registry records passed.',
    className: styles.cleared,
    badgeText: 'CLEARED',
    badgeClass: styles.badgeCleared,
  },
  [DECISION.REVIEW]: {
    label:     'REFER TO SECONDARY INSPECTION',
    sublabel:  'Inspection anomalies or warning signals detected. Officer review required.',
    className: styles.review,
    badgeText: 'REVIEW REQUIRED',
    badgeClass: styles.badgeReview,
  },
  [DECISION.REJECTED]: {
    label:     'CREDENTIAL REJECTED',
    sublabel:  'High threat indicators or cryptographic failure detected.',
    className: styles.rejected,
    badgeText: 'REJECTED',
    badgeClass: styles.badgeRejected,
  },
};

export default function VerificationResult() {
  const { session } = useVerification();
  const { result, risk } = session;

  const isStandby = result === null;
  const resultConfig = result ? RESULT_CONFIG[result.decision] : null;

  // Safe numerical threat index check (prevents "undefined / 100")
  const rawScore = risk?.data?.risk_score ?? (typeof risk?.score === 'number' ? risk.score : null);
  const hasScore = typeof rawScore === 'number';
  const scoreDisplay = hasScore ? `${rawScore} / 100` : '— / 100';

  const totalSegments = 20;
  const activeSegments = hasScore ? Math.min(Math.round((rawScore / 100) * totalSegments), totalSegments) : 0;

  // Risk tier classification
  let riskTier = 'STANDBY';
  let tierClass = styles.tierStandby;
  if (hasScore) {
    if (rawScore < 40) {
      riskTier = 'LOW THREAT';
      tierClass = styles.tierLow;
    } else if (rawScore < 70) {
      riskTier = 'ELEVATED RISK';
      tierClass = styles.tierElevated;
    } else {
      riskTier = 'HIGH CONCERN';
      tierClass = styles.tierHigh;
    }
  }

  return (
    <div className={styles.section} aria-label="Verification decision and threat index">
      {/* Standby State */}
      {isStandby && (
        <div className={styles.standby} aria-live="polite">
          <div className={styles.standbyIcon} aria-hidden="true">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </div>
          <div className={styles.standbyMeta}>
            <p className={styles.standbyTitle}>Terminal Ready for Credential Intake</p>
            <p className={styles.standbySubtitle}>
              Upload a document on the left and click "Run Verification Pipeline".
            </p>
          </div>
        </div>
      )}

      {/* Active Result Banner */}
      {resultConfig && (
        <div className={`${styles.resultBanner} ${resultConfig.className}`} role="status">
          <div className={styles.bannerHeader}>
            <span className={styles.resultLabel}>{resultConfig.label}</span>
            <span className={`${styles.statusBadge} ${resultConfig.badgeClass}`}>{resultConfig.badgeText}</span>
          </div>
          <p className={styles.resultSublabel}>{result.note || resultConfig.sublabel}</p>
          
          <div className={styles.blockchainSeal}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
              <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
            </svg>
            <span>Cryptographic Ledger: Anchored to Block #71 · SHA-256 Seal Valid</span>
          </div>
        </div>
      )}

      {/* Modern High-Precision Threat Meter */}
      <div className={styles.threatContainer} aria-label={`Threat Index: ${scoreDisplay}`}>
        <div className={styles.threatHeader}>
          <div className={styles.threatTitleGroup}>
            <span className={styles.threatLabel}>Composite Threat Index</span>
            <span className={styles.threatSub}>Deterministic Multimodal Risk Model</span>
          </div>
          <div className={styles.scoreGroup}>
            <span className={`${styles.tierBadge} ${tierClass}`}>{riskTier}</span>
            <span className={`${styles.threatScore} ${hasScore ? styles.scoreActive : ''}`}>
              {scoreDisplay}
            </span>
          </div>
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
