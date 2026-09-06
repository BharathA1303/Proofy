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
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                <path d="m9 12 2 2 4-4" />
              </svg>
            </div>
            <div className={styles.brandText}>
              <div className={styles.brandTitleRow}>
                <h1 className={styles.brandName}>Proofy</h1>
                <span className={styles.brandAiBadge}>AI</span>
              </div>
              <span className={styles.brandSubtitle}>Intelligent Document &amp; Identity Screening</span>
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
                Multi-Doc Case
              </button>
            </div>

            <span className={styles.systemIndicator} role="status" aria-label="System status: Operational">
              <span className={styles.statusDot} aria-hidden="true" />
              <span>System Operational</span>
            </span>
          </div>
        </div>
      </header>

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


