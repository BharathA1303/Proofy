/**
 * SidebarDrawer.jsx
 *
 * Responsive Left Navigation Drawer.
 * Controlled via hamburger button in the top navigation header.
 * Single Primary Section: Live Screening.
 */
import { useEffect } from 'react';
import styles from './SidebarDrawer.module.css';

export default function SidebarDrawer({
  isOpen,
  onClose,
}) {
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
                src="/avanza-mark.png"
                alt="Avanza Logo"
                className={styles.brandLogoImg}
              />
            </div>
            <div className={styles.brandText}>
              <div className={styles.brandTitleRow}>
                <span className={styles.brandName}>Avanza</span>
                <span className={styles.brandAiBadge}>AI</span>
              </div>
              <span className={styles.brandSubtitle}>Document &amp; Identity Screening</span>
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

        {/* Navigation Links */}
        <nav className={styles.navSection} aria-label="Main Navigation">
          <span className={styles.sectionHeader}>WORKSPACE</span>

          {/* Primary Nav Item: Live Screening */}
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
              <span className={styles.navDesc}>4-Stage Inspection Workbench</span>
            </div>
            <span className={styles.activeTag}>ACTIVE</span>
          </button>
        </nav>

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
              <span className={styles.widgetLabel}>Inspection Engine:</span>
              <span className={styles.widgetPrivacy}>Avanza AI Vision</span>
            </div>
            <div className={styles.widgetRow}>
              <span className={styles.widgetLabel}>Status:</span>
              <span className={styles.widgetVal}>Operational</span>
            </div>
          </div>
        </div>

        {/* Drawer Footer */}
        <div className={styles.panelFooter}>
          <div className={styles.footerVersionRow}>
            <span>Avanza Screening Engine</span>
            <span className={styles.verTag}>v2.4.0</span>
          </div>
          <span className={styles.footerLegal}>Enterprise Border &amp; Identity Security</span>
        </div>
      </aside>
    </div>
  );
}
