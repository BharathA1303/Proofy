/**
 * DocumentWorkspace.jsx
 *
 * Workspace layout replicating the exact 3-column + bottom dashboard structure
 * from the user's reference image:
 * - Row 1: 6-Stage Process Stepper
 * - Row 2 (3-Column Grid):
 *     1. UploadSection (Step 1: Upload Document + Dropzone + Doc Tabs + Tips)
 *     2. PipelineProgressCard (Verification Pipeline + Auto-run + 6 Steps)
 *     3. PreviewAndExtractedCard (Document Preview + Extracted Information)
 * - Row 3 (Bottom Row):
 *     1. RecentVerificationsTable (#, Type, DocNo, Name, Result, Risk, Time)
 *     2. SystemStatusCard (OCR, Biometric, Forensic, Risk, Database)
 */
import MilestoneStepper from '../milestone/MilestoneStepper.jsx';
import UploadSection from './UploadSection.jsx';
import PipelineProgressCard from './PipelineProgressCard.jsx';
import PreviewAndExtractedCard from './PreviewAndExtractedCard.jsx';
import RecentVerificationsTable from '../dashboard/RecentVerificationsTable.jsx';
import SystemStatusCard from '../dashboard/SystemStatusCard.jsx';
import styles from './DocumentWorkspace.module.css';

export default function DocumentWorkspace() {
  return (
    <div className={styles.workspaceContainer} role="region" aria-label="Verification Terminal">
      {/* ── 1. Top 6-Stage Process Stepper ── */}
      <MilestoneStepper />

      {/* ── 2. Three-Column Main Processing Grid ── */}
      <div className={styles.threeColumnGrid}>
        {/* Left Column: Upload & Ingestion */}
        <UploadSection />

        {/* Center Column: Verification Pipeline */}
        <PipelineProgressCard />

        {/* Right Column: Preview & Extracted Info */}
        <PreviewAndExtractedCard />
      </div>

      {/* ── 3. Bottom Row: Recent Verifications & System Status ── */}
      <div className={styles.bottomDashboardRow}>
        <RecentVerificationsTable />
        <SystemStatusCard />
      </div>
    </div>
  );
}
