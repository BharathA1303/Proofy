/**
 * PipelineProgressCard.jsx
 *
 * Center column of the 3-column workspace matching the exact reference image:
 * - Verification Pipeline title with 'Auto-run' toggle switch
 * - 6 vertical steps connected by a clean timeline line:
 *   1. Document Intake & OCR
 *   2. ICAO Validation
 *   3. Forensic Analysis
 *   4. Biometric Verification
 *   5. Risk Assessment
 *   6. Registry & Logging
 */
import { useState } from 'react';
import { useVerification } from '../../state/verification/useVerification.js';
import styles from './PipelineProgressCard.module.css';

const PIPELINE_STEPS = [
  { id: 1, key: 'extraction', title: 'Document Intake & OCR', desc: 'Extract text using OCR (MRZ, fields, images)' },
  { id: 2, key: 'validation', title: 'ICAO Validation', desc: 'Check digits, rules and document structure' },
  { id: 3, key: 'forensics',  title: 'Forensic Analysis', desc: 'Tamper detection, ELA and security features' },
  { id: 4, key: 'biometrics', title: 'Biometric Verification', desc: 'Face match and liveness detection (PAD)' },
  { id: 5, key: 'risk',       title: 'Risk Assessment', desc: 'AI-based threat scoring and rule engine' },
  { id: 6, key: 'registry',   title: 'Registry & Logging', desc: 'Save to database with decision and audit trail' },
];

export default function PipelineProgressCard() {
  const { session } = useVerification();
  const [autoRun, setAutoRun] = useState(true);

  const activeMilestone = session.activeMilestone || 0;
  const isCompleted = session.status === 'completed';

  function getStepStatus(stepNum) {
    if (isCompleted) return 'passed';
    if (activeMilestone === stepNum) return 'running';
    if (activeMilestone > stepNum) return 'passed';
    return 'pending';
  }

  return (
    <div className={styles.pipelineCard}>
      {/* Header */}
      <div className={styles.headerRow}>
        <h2 className={styles.cardTitle}>Verification Pipeline</h2>
        <div className={styles.autoRunControl}>
          <span className={styles.autoRunLabel}>Auto-run</span>
          <button
            type="button"
            role="switch"
            aria-checked={autoRun}
            className={`${styles.toggleSwitch} ${autoRun ? styles.toggleOn : ''}`}
            onClick={() => setAutoRun((v) => !v)}
          >
            <span className={styles.toggleKnob} />
          </button>
        </div>
      </div>

      {/* Timeline Steps List */}
      <div className={styles.timelineList}>
        {PIPELINE_STEPS.map((step, idx) => {
          const status = getStepStatus(step.id);
          const isLast = idx === PIPELINE_STEPS.length - 1;

          let badgeText = 'Pending';
          let badgeClass = styles.badgePending;

          if (status === 'running') {
            badgeText = 'Running...';
            badgeClass = styles.badgeRunning;
          } else if (status === 'passed') {
            badgeText = 'Passed';
            badgeClass = styles.badgePassed;
          }

          return (
            <div key={step.id} className={styles.timelineItem}>
              {/* Left Column: Number Node and Connecting Line */}
              <div className={styles.nodeColumn}>
                <div className={`${styles.nodeCircle} ${status === 'passed' ? styles.nodePassed : status === 'running' ? styles.nodeRunning : styles.nodePending}`}>
                  {status === 'running' ? (
                    <svg className={styles.spinner} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                      <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="12" />
                    </svg>
                  ) : status === 'passed' ? (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  ) : (
                    <span>{step.id}</span>
                  )}
                </div>
                {!isLast && (
                  <div className={`${styles.connectingLine} ${status === 'passed' ? styles.lineDone : ''}`} aria-hidden="true" />
                )}
              </div>

              {/* Center Column: Title & Description */}
              <div className={styles.stepContent}>
                <h3 className={styles.stepTitle}>{step.title}</h3>
                <p className={styles.stepDescription}>{step.desc}</p>
              </div>

              {/* Right Column: Status Pill */}
              <div className={styles.statusCol}>
                <span className={`${styles.statusPill} ${badgeClass}`}>
                  <span className={styles.statusDot} aria-hidden="true" />
                  <span>{badgeText}</span>
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
