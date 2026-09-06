/**
 * TopNavBar.jsx
 *
 * Replicates the exact header from the target design:
 * Brand title + Tagline + Theme toggle + SIH Sandbox pill + System status + User avatar pill
 */
import { useState } from 'react';
import styles from './TopNavBar.module.css';

export default function TopNavBar() {
  const [sandboxDropdownOpen, setSandboxDropdownOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  return (
    <header className={styles.navBar} role="banner">
      <div className={styles.navLeft}>
        <div className={styles.brandGroup}>
          <div className={styles.brandIconBox} aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              <path d="m9 12 2 2 4-4" />
            </svg>
          </div>
          <div className={styles.brandTitles}>
            <span className={styles.brandName}>Document Verification System</span>
          </div>
        </div>
        <span className={styles.dividerPipe} aria-hidden="true">|</span>
        <span className={styles.tagline}>Secure Identities. Safer Journeys. Trusted Borders.</span>
      </div>

      <div className={styles.navRight}>
        {/* Theme toggle button */}
        <button
          type="button"
          className={styles.themeToggleBtn}
          title="Toggle color theme"
          aria-label="Toggle color theme"
        >
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="5" />
            <line x1="12" y1="1" x2="12" y2="3" />
            <line x1="12" y1="21" x2="12" y2="23" />
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
            <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
            <line x1="1" y1="12" x2="3" y2="12" />
            <line x1="21" y1="12" x2="23" y2="12" />
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
            <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
          </svg>
        </button>

        {/* SIH Sandbox dropdown pill */}
        <div className={styles.sandboxDropdownWrapper}>
          <button
            type="button"
            className={styles.sandboxPill}
            onClick={() => setSandboxDropdownOpen((v) => !v)}
            aria-expanded={sandboxDropdownOpen}
          >
            <span>SIH Sandbox</span>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
        </div>

        {/* System operational badge */}
        <div className={styles.systemStatusPill}>
          <span className={styles.statusDot} aria-hidden="true" />
          <span>System Operational</span>
        </div>

        {/* User profile avatar pill */}
        <div className={styles.userProfileWrapper}>
          <button
            type="button"
            className={styles.userProfileBtn}
            onClick={() => setUserMenuOpen((v) => !v)}
            aria-expanded={userMenuOpen}
          >
            <div className={styles.avatarCircle}>B</div>
            <div className={styles.userInfo}>
              <span className={styles.userName}>Bharath A</span>
              <span className={styles.userRole}>Inspector</span>
            </div>
            <svg className={styles.chevronIcon} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
        </div>
      </div>
    </header>
  );
}
