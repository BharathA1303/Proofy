/**
 * DocumentWorkspace.jsx
 *
 * Unified Document Verification Workbench.
 * Orchestrates the 4-stage progressive officer screening workflow:
 *   Stage 1: Document Intake (Type & Upload)
 *   Stage 2: Officer Inspection (Credential & Registry Dossier)
 *   Stage 3: Live Biometrics (Camera Face Verification)
 *   Stage 4: Clearance Decision (Official Disposition Dossier)
 */
import { useVerification } from '../../state/verification/useVerification.js';
import StageStepper from '../workflow/StageStepper.jsx';
import Stage1Intake from '../workflow/Stage1Intake.jsx';
import Stage2Inspection from '../workflow/Stage2Inspection.jsx';
import Stage3Biometrics from '../workflow/Stage3Biometrics.jsx';
import Stage4Clearance from '../workflow/Stage4Clearance.jsx';
import styles from './DocumentWorkspace.module.css';

export default function DocumentWorkspace() {
  const { session } = useVerification();
  const currentStage = session.workflowStage || 1;

  return (
    <div
      className={styles.workspace}
      id={`tabpanel-${session.documentType}`}
      role="tabpanel"
      aria-labelledby={`tab-${session.documentType}`}
    >
      {/* 4-Stage Workflow Stepper */}
      <StageStepper />

      {/* Progressive Stage Content */}
      <div className={styles.stageContent}>
        {currentStage === 1 && <Stage1Intake />}
        {currentStage === 2 && <Stage2Inspection />}
        {currentStage === 3 && <Stage3Biometrics />}
        {currentStage === 4 && <Stage4Clearance />}
      </div>
    </div>
  );
}
