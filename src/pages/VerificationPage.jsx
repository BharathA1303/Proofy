/**
 * VerificationPage.jsx
 *
 * Replicates the exact layout from the reference image:
 * 1. TopNavBar: Brand, Tagline, Theme toggle, SIH Sandbox pill, System Operational, Inspector avatar
 * 2. HeroStatsBar: Welcome greeting, real-time clock, 4 KPI stats (128 Verified, 122 Clear, 5 Review, 1 High Risk)
 * 3. DocumentWorkspace:
 *    - 6-step horizontal milestone process flow
 *    - 3-column workstation grid (UploadSection | PipelineProgressCard | PreviewAndExtractedCard)
 *    - Bottom dashboard row (RecentVerificationsTable | SystemStatusCard)
 */
import { useState } from 'react';
import TopNavBar from '../components/dashboard/TopNavBar.jsx';
import HeroStatsBar from '../components/dashboard/HeroStatsBar.jsx';
import DocumentWorkspace from '../components/document/DocumentWorkspace.jsx';
import VerificationCase from '../components/case/VerificationCase.jsx';
import styles from './VerificationPage.module.css';

export default function VerificationPage() {
  const [workspaceMode, setWorkspaceMode] = useState('single'); // 'single' | 'case'

  return (
    <div className={styles.page}>
      {/* ── 1. Top Navigation Bar ── */}
      <TopNavBar />

      {/* ── 2. Main Content Container ── */}
      <main className={styles.main} id="main-content">
        {/* Workspace Mode Switcher Ribbon */}
        <div className={styles.modeBar}>
          <div className={styles.modeSwitcher} role="tablist" aria-label="Screening Workspace Mode">
            <button
              type="button"
              role="tab"
              aria-selected={workspaceMode === 'single'}
              className={`${styles.modeButton} ${workspaceMode === 'single' ? styles.modeButtonActive : ''}`}
              onClick={() => setWorkspaceMode('single')}
              id="tab-single-doc-mode"
            >
              Single Document Screening
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={workspaceMode === 'case'}
              className={`${styles.modeButton} ${workspaceMode === 'case' ? styles.modeButtonActive : ''}`}
              onClick={() => setWorkspaceMode('case')}
              id="tab-case-mode"
            >
              Multi-Doc Case (M1–M12)
            </button>
          </div>
        </div>

        {/* Hero Greeting & Live KPI Metrics */}
        <HeroStatsBar />

        {/* Core Workspace */}
        {workspaceMode === 'single' ? (
          <DocumentWorkspace />
        ) : (
          <VerificationCase />
        )}
      </main>
    </div>
  );
}
