/**
 * SidebarDrawer.jsx
 *
 * Responsive Left Navigation Drawer.
 * Controlled via hamburger button in the top navigation header.
 * Houses:
 *   - Clean Meiyari branding
 *   - Inspection Workflow Stages (relocated cleanly from navbar)
 *   - Active Inspection Station Diagnostics & Officer Identity
 *   - Lock Terminal & Sign Out Action
 */
import { useEffect } from 'react';
import { useAuth } from '../../state/auth/useAuth.js';
import { useVerification } from '../../state/verification/useVerification.js';
import styles from './SidebarDrawer.module.css';

const WORKFLOW_STAGES = [
  {
    id: 1,
    title: '1. Document Intake',
    desc: 'Category & Document Upload',
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
    desc: 'Credential & Registry Dossier',
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        <path d="m9 12 2 2 4-4" />
      </svg>
    ),
  },
  {
    id: 3,
    title: '3. Face Verification',
    desc: 'Live Camera Biometrics',
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
        <circle cx="12" cy="13" r="4" />
      </svg>
    ),
  },
  {
    id: 4,
    title: '4. Clearance Decision',
    desc: 'Official Admission Verdict',
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <path d="m9 12 2 2 4-4" />
      </svg>
    ),
  },
];

export default function SidebarDrawer({
  isOpen,
  onClose,
}) {
  const { officer, logout } = useAuth();
  const { session, actions } = useVerification();
  const currentStage = session.workflowStage || 1;
  const maxUnlocked = session.maxUnlockedStage || 1;

  // Close drawer on Escape key press
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Prevent background body scroll when drawer is open on mobile
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className={styles.drawerRoot} role="dialog" aria-modal="true" aria-label="Navigation Menu">
      {/* Frosted Backdrop */}
      <div className={styles.backdrop} onClick={onClose} aria-hidden="true" />

      {/* Slide-out Panel */}
      <aside className={styles.panel}>
        {/* Drawer Header */}
        <div className={styles.panelHeader}>
          <div className={styles.brand}>
            <div className={styles.brandBadge}>
              <img
                src="/meiyari-mark.png"
                alt="Meiyari Logo"
                className={styles.brandLogoImg}
              />
            </div>
            <div className={styles.brandText}>
              <span className={styles.brandName}>MEIYARI</span>
            </div>
          </div>

          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            aria-label="Close navigation menu"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Primary Navigation Item */}
        <nav className={styles.navSection} aria-label="Main Navigation">
          <span className={styles.sectionHeader}>WORKSPACE</span>

          <button
            type="button"
            className={`${styles.navItem} ${styles.navItemActive}`}
            onClick={onClose}
          >
            <div className={styles.navIcon}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="12" y1="18" x2="12" y2="12" />
                <line x1="9" y1="15" x2="15" y2="15" />
              </svg>
            </div>
            <div className={styles.navTextCol}>
              <span className={styles.navTitle}>Live Screening</span>
              <span className={styles.navDesc}>Border Clearance Terminal</span>
            </div>
            <span className={styles.activeTag}>ACTIVE</span>
          </button>
        </nav>

        {/* Inspection Stages Progression (Relocated cleanly from navbar) */}
        <div className={styles.stagesSection}>
          <div className={styles.stagesSectionHeader}>
            <span className={styles.sectionHeader}>INSPECTION STAGES</span>
            <span className={styles.stageProgressText}>Stage {currentStage} of 4</span>
          </div>

          <div className={styles.stagesList}>
            {WORKFLOW_STAGES.map((stg) => {
              const isActive = currentStage === stg.id;
              const isCompleted = currentStage > stg.id || stg.id < maxUnlocked;
              const isUnlocked = stg.id <= maxUnlocked;

              return (
                <button
                  key={stg.id}
                  type="button"
                  className={`${styles.stageDrawerItem} ${
                    isActive
                      ? styles.stageDrawerActive
                      : isCompleted
                      ? styles.stageDrawerCompleted
                      : styles.stageDrawerLocked
                  }`}
                  onClick={() => {
                    if (isUnlocked) {
                      actions.setWorkflowStage(stg.id);
                      onClose();
                    }
                  }}
                  disabled={!isUnlocked}
                  title={isUnlocked ? `Switch to ${stg.title}` : 'Complete prior stage to unlock'}
                >
                  <div className={styles.stageItemLeft}>
                    <div className={styles.stageNumberBadge}>
                      {isCompleted && !isActive ? (
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      ) : (
                        stg.icon
                      )}
                    </div>
                    <div className={styles.stageItemInfo}>
                      <span className={styles.stageItemTitle}>{stg.title}</span>
                      <span className={styles.stageItemDesc}>{stg.desc}</span>
                    </div>
                  </div>

                  <div className={styles.stageStatusCol}>
                    {isActive && <span className={styles.badgeCurrent}>CURRENT</span>}
                    {isCompleted && !isActive && <span className={styles.badgeDone}>DONE</span>}
                    {!isUnlocked && (
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" className={styles.lockIcon}>
                        <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                        <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                      </svg>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* System & Station Diagnostics Widget */}
        <div className={styles.nodeWidget}>
          <div className={styles.widgetHeader}>
            <span className={styles.widgetTitle}>INSPECTION STATION</span>
            <span className={styles.syncDot} title="System Connected & Operational" />
          </div>

          <div className={styles.widgetRows}>
            <div className={styles.widgetRow}>
              <span className={styles.widgetLabel}>Terminal:</span>
              <span className={styles.widgetVal}>T3 - Gate 14</span>
            </div>
            <div className={styles.widgetRow}>
              <span className={styles.widgetLabel}>Mode:</span>
              <span className={styles.widgetVal}>Officer Clearance</span>
            </div>
            <div className={styles.widgetRow}>
              <span className={styles.widgetLabel}>Status:</span>
              <span className={styles.widgetVal}>Operational</span>
            </div>
            {officer && (
              <div className={styles.widgetRow}>
                <span className={styles.widgetLabel}>Officer:</span>
                <span className={styles.widgetVal}>{officer.name}</span>
              </div>
            )}
          </div>

          <button
            type="button"
            className={styles.drawerSignOutBtn}
            onClick={() => {
              onClose();
              logout();
            }}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            <span>Lock Terminal &amp; Sign Out</span>
          </button>
        </div>

        {/* Drawer Footer */}
        <div className={styles.panelFooter}>
          <div className={styles.footerVersionRow}>
            <span>Meiyari Screening System</span>
            <span className={styles.verTag}>v2.4.0</span>
          </div>
          <span className={styles.footerLegal}>Enterprise Border &amp; Identity Security</span>
        </div>
      </aside>
    </div>
  );
}
