/**
 * VerificationPage.jsx
 *
 * The root page of the application.
 * Composes:
 *   - Clean enterprise header with hamburger navigation and integrated workflow stepper
 *   - Responsive left sidebar drawer
 *   - Unified DocumentWorkspace (Live Screening)
 */
import { useEffect, useState } from 'react';
import { useVerification } from '../state/verification/useVerification.js';
import { useAuth } from '../state/auth/useAuth.js';
import DocumentWorkspace from '../components/document/DocumentWorkspace.jsx';
import StageStepper from '../components/workflow/StageStepper.jsx';
import SidebarDrawer from '../components/navigation/SidebarDrawer.jsx';
import styles from './VerificationPage.module.css';

export default function VerificationPage() {
  const [isBackendHealthy, setIsBackendHealthy] = useState(true);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const { actions } = useVerification();
  const { officer, logout } = useAuth();

  useEffect(() => {
    let isMounted = true;
    async function checkHealth() {
      try {
        const res = await fetch('/api/v1/system/health');
        if (isMounted) setIsBackendHealthy(res.ok);
      } catch {
        if (isMounted) setIsBackendHealthy(false);
      }
    }
    checkHealth();
    const interval = setInterval(checkHealth, 8000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <div className={styles.page}>
      {/* Clean enterprise header */}
      <header className={styles.header} role="banner">
        <div className={styles.headerInner}>
          <div className={styles.headerLeftGroup}>
            {/* Hamburger Button for Left Sidebar Drawer */}
            <button
              type="button"
              className={styles.hamburgerBtn}
              onClick={() => setIsDrawerOpen(true)}
              aria-label="Open navigation menu"
              aria-expanded={isDrawerOpen}
              title="Open Navigation Menu"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>

            <div className={styles.brand}>
              <div className={styles.brandBadge}>
                <img
                  src="/meiyari-mark.png"
                  alt="Meiyari Logo Mark"
                  className={styles.brandLogoImg}
                />
              </div>
              <div className={styles.brandText}>
                <div className={styles.brandTitleRow}>
                  <h1 className={styles.brandName}>Meiyari</h1>
                  <span className={styles.brandAiBadge}>AI</span>
                </div>
                <span className={styles.brandSubtitle}>AI-Powered Identity &amp; Document Verification</span>
              </div>
            </div>
          </div>

          {/* Desktop Center: Integrated Workflow Stepper */}
          <div className={styles.headerCenter}>
            <StageStepper isHeader={true} />
          </div>

          <div className={styles.headerRight}>
            <div className={styles.officerPill} title={`Duty Station: ${officer?.station || 'Station T3'} • ${officer?.clearanceLevel || 'Level 3'}`}>
              <div className={styles.officerAvatar}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
              </div>
              <div className={styles.officerMeta}>
                <span className={styles.officerName}>{officer?.name || 'Insp. S. Raman'}</span>
                <span className={styles.officerStation}>{officer?.station || 'T3 · Gate 4'}</span>
              </div>
              <span
                className={`${styles.statusDot} ${isBackendHealthy ? styles.statusDotActive : styles.statusDotOffline}`}
                title={isBackendHealthy ? 'Terminal Synced & Active' : 'Registry Offline'}
              />
            </div>

            <button
              type="button"
              className={styles.headerResetBtn}
              onClick={() => actions.resetSession()}
              title="Reset inspection workflow"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
                <path d="M21 3v5h-5" />
                <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
                <path d="M8 16H3v5" />
              </svg>
              <span>Reset</span>
            </button>

            <button
              type="button"
              className={styles.headerLogoutBtn}
              onClick={() => logout()}
              title="Lock Terminal & Sign Out"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
            </button>
          </div>
        </div>
      </header>

      {/* Mobile/Tablet Sub-Header Ribbon Stepper */}
      <div className={styles.mobileStepperRibbon}>
        <StageStepper isMobile={true} />
      </div>

      {/* Main Content Area: Live Screening */}
      <main className={styles.main} id="main-content">
        <DocumentWorkspace />
      </main>

      {/* Responsive Left Navigation Drawer */}
      <SidebarDrawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
      />
    </div>
  );
}
