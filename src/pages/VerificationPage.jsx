/**
 * VerificationPage.jsx
 *
 * The root page of the application.
 * Composes: Clean enterprise header + Unified DocumentWorkspace.
 */
import { useEffect, useState } from 'react';
import DocumentWorkspace from '../components/document/DocumentWorkspace.jsx';
import styles from './VerificationPage.module.css';

export default function VerificationPage() {
  const [isBackendHealthy, setIsBackendHealthy] = useState(true);

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
          <div className={styles.brand}>
            <div className={styles.brandBadge}>
              <img
                src="/avanza-mark.png"
                alt="Avanza Logo Mark"
                className={styles.brandLogoImg}
              />
            </div>
            <div className={styles.brandText}>
              <div className={styles.brandTitleRow}>
                <h1 className={styles.brandName}>Avanza</h1>
                <span className={styles.brandAiBadge}>AI</span>
              </div>
              <span className={styles.brandSubtitle}>Intelligent Document &amp; Identity Screening</span>
            </div>
          </div>

          <div className={styles.headerRight}>
            <span
              className={`${styles.systemIndicator} ${isBackendHealthy ? styles.indicatorOnline : styles.indicatorOffline}`}
              role="status"
              aria-label={`System status: ${isBackendHealthy ? 'Operational' : 'Backend Offline'}`}
              title={isBackendHealthy ? 'FastAPI Backend is connected & operational' : 'Backend offline on port 8000. Start with: python -m uvicorn app.main:app --port 8000'}
            >
              <span className={`${styles.statusDot} ${!isBackendHealthy ? styles.statusDotOffline : ''}`} aria-hidden="true" />
              <span>{isBackendHealthy ? 'System Operational' : 'Backend Offline'}</span>
            </span>
          </div>
        </div>
      </header>

      <main className={styles.main} id="main-content">
        <DocumentWorkspace />
      </main>
    </div>
  );
}


