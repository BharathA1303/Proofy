/**
 * MilestoneStepper.jsx
 *
 * 6-Stage Process Flow replicating the exact design from the reference image:
 *   (1) Upload Document (Passport / Visa / ID)
 *   (2) Extract & Validate (OCR + ICAO checks)
 *   (3) Forensic Analysis (Tamper + ELA scan)
 *   (4) Biometric Match (Face + PAD)
 *   (5) Risk Assessment (AI threat scoring)
 *   (6) Result & Registry (Save & log decision)
 */
import { useVerification } from '../../state/verification/useVerification.js';
import styles from './MilestoneStepper.module.css';

const STEPS = [
  { key: 'upload',     num: 1, label: 'Upload Document',   sub: 'Passport / Visa / ID' },
  { key: 'extraction', num: 2, label: 'Extract & Validate', sub: 'OCR + ICAO checks' },
  { key: 'forensics',  num: 3, label: 'Forensic Analysis',  sub: 'Tamper + ELA scan' },
  { key: 'biometrics', num: 4, label: 'Biometric Match',    sub: 'Face + PAD' },
  { key: 'risk',       num: 5, label: 'Risk Assessment',   sub: 'AI threat scoring' },
  { key: 'registry',   num: 6, label: 'Result & Registry', sub: 'Save & log decision' },
];

export default function MilestoneStepper() {
  const { session } = useVerification();
  const activeMilestone = session.activeMilestone || 0;
  const milestones = session.milestones || {};
  const isCompleted = session.status === 'completed';

  return (
    <div className={styles.stepperContainer} aria-label="Verification Workflow Stages">
      <div className={styles.stepsWrapper}>
        {STEPS.map((step, idx) => {
          const isCurrent = (activeMilestone === 0 && idx === 0) || activeMilestone === step.num;
          const isPassed = isCompleted || (activeMilestone > step.num);
          const isRunning = activeMilestone === step.num && !isCompleted;
          const isLast = idx === STEPS.length - 1;

          let circleClass = styles.circleIdle;
          if (isRunning) circleClass = styles.circleRunning;
          else if (isPassed) circleClass = styles.circlePassed;
          else if (isCurrent) circleClass = styles.circleActive;

          return (
            <div key={step.key} className={styles.stepBlock}>
              <div className={styles.nodeRow}>
                {/* Step Circle Badge */}
                <div className={`${styles.circle} ${circleClass}`}>
                  {isRunning ? (
                    <svg className={styles.spinner} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                      <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="12" />
                    </svg>
                  ) : isPassed ? (
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  ) : (
                    <span>{step.num}</span>
                  )}
                </div>

                {/* Connecting horizontal line */}
                {!isLast && (
                  <div
                    className={`${styles.connectorLine} ${isPassed ? styles.linePassed : ''}`}
                    aria-hidden="true"
                  />
                )}
              </div>

              {/* Step Labels */}
              <div className={styles.labelWrapper}>
                <span className={`${styles.stepTitle} ${isCurrent ? styles.titleActive : ''}`}>
                  {step.label}
                </span>
                <span className={styles.stepSubtitle}>{step.sub}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
