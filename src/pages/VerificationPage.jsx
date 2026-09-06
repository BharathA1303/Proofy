/**
 * VerificationPage.jsx
 *
 * The root page of the application.
 * Composes: Clean enterprise header + DocumentSelector tabs + Unified DocumentWorkspace.
 */
import { useState } from 'react';
import { APP_NAME, APP_SHORT_NAME, APP_VERSION } from '../config/appConfig.js';
import DocumentSelector from '../components/document/DocumentSelector.jsx';
import DocumentWorkspace from '../components/document/DocumentWorkspace.jsx';
import VerificationCase from '../components/case/VerificationCase.jsx';
import styles from './VerificationPage.module.css';

export default function VerificationPage() {
  const [workspaceMode, setWorkspaceMode] = useState('single'); // 'single' | 'case'

  return (
    <div className={styles.page}>
      {/* Clean enterprise header */}
      <header className={styles.header} role="banner">
        <div className={styles.headerInner}>
          <div className={styles.brand}>
            <div className={styles.brandBadge}>
              <span className={styles.brandMark} aria-hidden="true">
                {APP_SHORT_NAME}
              </span>
            </div>
            <div className={styles.brandText}>
              <h1 className={styles.brandName}>{APP_NAME}</h1>
              <span className={styles.brandVersion}>Automated Screening Terminal · {APP_VERSION}</span>
            </div>
          </div>

          <div className={styles.headerRight}>
            {/* Mode Switcher */}
            <div className={styles.modeSwitcher} role="tablist" aria-label="Screening Workspace Mode">
              <button
                type="button"
                role="tab"
                aria-selected={workspaceMode === 'single'}
                className={`${styles.modeButton} ${workspaceMode === 'single' ? styles.modeButtonActive : ''}`}
                onClick={() => setWorkspaceMode('single')}
                id="tab-single-doc-mode"
              >
                Single Document
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

            <span className={styles.systemIndicator} role="status" aria-label="System status: Operational">
              <span className={styles.statusDot} aria-hidden="true" />
              <span>System Operational</span>
            </span>
          </div>
        </div>
      </header>

      {/* SIH Evaluation Sandbox & Demonstration Banner */}
      <div className={styles.sandboxBanner} role="status">
        <div className={styles.sandboxInner}>
          <span className={styles.sandboxBadge}>DEMONSTRATION / SANDBOX MODE</span>
          <span className={styles.sandboxDetails}>
            <strong>Environment:</strong> SIH Evaluation Sandbox &bull;{' '}
            <strong>Registry:</strong> Development Mock &bull;{' '}
            <strong>Blockchain Audit:</strong> Local Cryptographic Ledger &bull;{' '}
            <strong>System:</strong> AI-Assisted Decision Support (Non-Autonomous)
          </span>
        </div>
      </div>

      {workspaceMode === 'single' ? (
        <>
          {/* Document type tab bar */}
          <DocumentSelector />

          {/* Main verification workspace */}
          <main className={styles.main} id="main-content">
            <DocumentWorkspace />
          </main>
        </>
      ) : (
        <main className={styles.main} id="main-content">
          <VerificationCase />
        </main>
      )}
    </div>
  );
}


