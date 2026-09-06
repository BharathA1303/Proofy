/**
 * MilestoneStepper.jsx
 *
 * Visual 5-stage progressive milestone pipeline for document verification.
 * Displays sequential verification progress across:
 *   1. Ingestion & Extraction (OCR / MRZ)
 *   2. Document Format & Checksum Validation
 *   3. Forensic Tampering & ELA Analysis
 *   4. Biometric Face Match & PAD Liveness
 *   5. Registry Cross-Check & Composite Risk Decision
 */
import { useVerification } from '../../state/verification/useVerification.js';
import styles from './MilestoneStepper.module.css';

const STEPS = [
  { key: 'extraction', label: '1. Intake & OCR', desc: 'Field & MRZ extraction' },
  { key: 'validation', label: '2. Validation', desc: 'ICAO check digits & rules' },
  { key: 'forensics',  label: '3. Forensics', desc: 'Tamper & ELA scan' },
  { key: 'biometrics', label: '4. Biometrics', desc: 'Facial match & PAD' },
  { key: 'registryRisk', label: '5. Risk & Registry', desc: 'Database & decision' },
];

export default function MilestoneStepper() {
  const { session } = useVerification();
  const milestones = session.milestones || {};
  const activeMilestone = session.activeMilestone || 0;

  // Calculate overall state description
  let activeText = 'Pipeline Standby — Awaiting Document';
  if (activeMilestone > 0 && activeMilestone <= 5) {
    const activeKey = STEPS[activeMilestone - 1]?.key;
    const current = milestones[activeKey];
    activeText = `Milestone ${activeMilestone}/5: ${current?.label || 'Processing'} (${current?.desc || 'Running evaluation'})`;
  } else if (session.status === 'completed') {
    activeText = 'Inspection Complete — All Milestones Evaluated';
  }

  return (
    <div className={styles.container} aria-label="Verification Pipeline Milestones">
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <span className={styles.title}>Inspection Pipeline Stages</span>
        </div>
        <div className={styles.activeStageBadge} role="status">
          {activeMilestone > 0 && activeMilestone <= 5 && (
            <svg className={styles.spinner} width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
              <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="12" />
            </svg>
          )}
          <span>{activeText}</span>
        </div>
      </div>

      <div className={styles.stepperRow} role="progressbar" aria-valuenow={activeMilestone} aria-valuemin="0" aria-valuemax="5">
        {STEPS.map((step, idx) => {
          const stepData = milestones[step.key] || { status: 'idle' };
          const status = stepData.status || 'idle';
          const isLast = idx === STEPS.length - 1;

          // Connector state
          let connectorClass = '';
          if (status === 'passed') connectorClass = styles.connectorPassed;
          else if (status === 'running') connectorClass = styles.connectorRunning;

          return (
            <div key={step.key} className={`${styles.stepItem} ${styles['step_' + status] || styles.step_idle}`}>
              <div className={styles.stepIconBox}>
                {status === 'running' ? (
                  <svg className={styles.spinner} width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="12" />
                  </svg>
                ) : status === 'passed' ? (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                ) : status === 'warning' ? (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
                    <line x1="12" y1="9" x2="12" y2="13" />
                    <line x1="12" y1="17" x2="12.01" y2="17" />
                  </svg>
                ) : status === 'failed' ? (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="15" y1="9" x2="9" y2="15" />
                    <line x1="9" y1="9" x2="15" y2="15" />
                  </svg>
                ) : (
                  <span>{idx + 1}</span>
                )}
              </div>

              {!isLast && (
                <div className={`${styles.stepConnector} ${connectorClass}`} aria-hidden="true" />
              )}

              <div className={styles.labelGroup}>
                <span className={styles.stepName}>{step.label}</span>
                <span className={styles.stepDesc}>{step.desc}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
