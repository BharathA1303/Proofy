/**
 * SidebarDrawer.jsx
 *
 * Responsive Left Navigation Drawer.
 * Controlled via hamburger button in the top navigation header.
 * Houses:
 *   - Clean Meiyari branding
 *   - Navigation items
 *   - Dedicated User Profile & Account Section
 */
import { useEffect } from 'react';
import { useAuth } from '../../state/auth/useAuth.js';
import styles from './SidebarDrawer.module.css';

export default function SidebarDrawer({
  isOpen,
  onClose,
}) {
  const { officer, logout } = useAuth();

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
              <span className={styles.navDesc}>Document Verification Terminal</span>
            </div>
            <span className={styles.activeTag}>ACTIVE</span>
          </button>
        </nav>

        {/* Dedicated User Profile Section (Transfer from diagnostics box) */}
        <div className={styles.profileSection}>
          <span className={styles.sectionHeader}>PROFILE &amp; ACCOUNT</span>

          <div className={styles.profileCard}>
            <div className={styles.profileHeader}>
              <div className={styles.profileAvatar}>
                {officer?.name ? (
                  officer.name
                    .split(' ')
                    .map((n) => n[0])
                    .slice(0, 2)
                    .join('')
                    .toUpperCase()
                ) : (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                    <circle cx="12" cy="7" r="4" />
                  </svg>
                )}
              </div>

              <div className={styles.profileMeta}>
                <span className={styles.profileName}>{officer?.name || 'Verified User'}</span>
                <span className={styles.profileRole}>{officer?.role || 'Verification Officer'}</span>
              </div>

              <span className={styles.statusPillBadge} title="Authenticated & Active">
                <span className={styles.statusPillDot} />
                <span>Active</span>
              </span>
            </div>

            <div className={styles.profileDetailsList}>
              <div className={styles.profileDetailRow}>
                <span className={styles.detailLabel}>Email / ID</span>
                <span className={styles.detailValue}>{officer?.email || officer?.id || 'officer@meiyari.gov'}</span>
              </div>
              <div className={styles.profileDetailRow}>
                <span className={styles.detailLabel}>Duty Station</span>
                <span className={styles.detailValue}>{officer?.station || 'Terminal 3 · Gate 4'}</span>
              </div>
              <div className={styles.profileDetailRow}>
                <span className={styles.detailLabel}>Clearance Level</span>
                <span className={styles.detailValue}>{officer?.clearanceLevel || 'Level 3 Access'}</span>
              </div>
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
              <span>Sign Out</span>
            </button>
          </div>
        </div>

        {/* Drawer Footer */}
        <div className={styles.panelFooter}>
          <div className={styles.footerVersionRow}>
            <span>Meiyari Platform</span>
            <span className={styles.verTag}>v2.4.0</span>
          </div>
          <span className={styles.footerLegal}>Enterprise Identity Security</span>
        </div>
      </aside>
    </div>
  );
}
