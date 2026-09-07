/**
 * StageStepper.jsx
 *
 * Professional 4-Stage Workflow Stepper for Border & Transport Inspection Officers.
 * Stages:
 *   Stage 1: Document Intake (Type & Upload)
 *   Stage 2: Officer Inspection (Credential & Registry Dossier)
 *   Stage 3: Live Face Match (Webcam Biometric Verification)
 *   Stage 4: Final Clearance (Admission Decision & Official Dossier)
 */
import { useVerification } from '../../state/verification/useVerification.js';
import styles from './StageStepper.module.css';

const STAGES = [
  {
    id: 1,
    title: '1. Document Intake',
    subtitle: 'Category & Document Upload',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="12" y1="18" x2="12" y2="12" />
        <line x1="9" y1="15" x2="15" y2="15" />
      </svg>
    ),
  },
  {
    id: 2,
    title: '2. Officer Inspection',
    subtitle: 'Security & Registry Review',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        <path d="m9 12 2 2 4-4" />
      </svg>
    ),
  },
  {
    id: 3,
    title: '3. Live Biometrics',
    subtitle: 'Camera Face Match',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
        <circle cx="12" cy="13" r="4" />
      </svg>
    ),
  },
  {
    id: 4,
    title: '4. Clearance Decision',
    subtitle: 'Final Officer Verdict',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <path d="m9 12 2 2 4-4" />
      </svg>
    ),
  },
];

export default function StageStepper() {
  const { session, actions } = useVerification();
  const currentStage = session.workflowStage || 1;
  const maxUnlocked = session.maxUnlockedStage || 1;

  function handleStageClick(stageId) {
    if (stageId <= maxUnlocked) {
      actions.setWorkflowStage(stageId);
    }
  }

  return (
    <div className={styles.stepperContainer} role="navigation" aria-label="Inspection Workflow Steps">
      <div className={styles.stepperTrack}>
        {STAGES.map((stage, idx) => {
          const isCompleted = currentStage > stage.id || (stage.id < maxUnlocked);
          const isActive = currentStage === stage.id;
          const isAccessible = stage.id <= maxUnlocked;
          const isLast = idx === STAGES.length - 1;

          let stepStateClass = styles.stepLocked;
          if (isActive) stepStateClass = styles.stepActive;
          else if (isCompleted) stepStateClass = styles.stepCompleted;
          else if (isAccessible) stepStateClass = styles.stepAccessible;

          return (
            <div key={stage.id} className={styles.stageWrapper}>
              <button
                type="button"
                className={`${styles.stepButton} ${stepStateClass}`}
                onClick={() => handleStageClick(stage.id)}
                disabled={!isAccessible}
                aria-current={isActive ? 'step' : undefined}
                title={isAccessible ? `Go to ${stage.title}` : `Complete previous stages first`}
              >
                <div className={styles.iconCircle}>
                  {isCompleted && !isActive ? (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  ) : (
                    stage.icon
                  )}
                </div>

                <div className={styles.labelBlock}>
                  <span className={styles.stepTitle}>{stage.title}</span>
                  <span className={styles.stepSubtitle}>{stage.subtitle}</span>
                </div>

                {isActive && <div className={styles.activePill}>CURRENT</div>}
              </button>

              {!isLast && (
                <div
                  className={`${styles.connectorLine} ${stage.id < maxUnlocked ? styles.connectorPassed : ''}`}
                  aria-hidden="true"
                />
              )}
            </div>
          );
        })}
      </div>

      <div className={styles.stepperRight}>
        <button
          type="button"
          className={styles.resetBtn}
          onClick={() => actions.resetSession()}
          title="Reset inspection session"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
            <path d="M21 3v5h-5" />
            <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
            <path d="M8 16H3v5" />
          </svg>
          <span>Reset Inspection</span>
        </button>
      </div>
    </div>
  );
}
