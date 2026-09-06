/**
 * HeroStatsBar.jsx
 *
 * Replicates the exact welcome greeting, date/time card, and 4 KPI metrics tiles:
 * - 128 Verified Today (Blue)
 * - 122 Clear (Green)
 * - 5 Needs Review (Amber)
 * - 1 High Risk (Red)
 */
import { useEffect, useState } from 'react';
import styles from './HeroStatsBar.module.css';

export default function HeroStatsBar() {
  const [currentDateStr, setCurrentDateStr] = useState('Sat, 06 Sep 2026');
  const [currentTimeStr, setCurrentTimeStr] = useState('10:24 AM');

  useEffect(() => {
    function updateClock() {
      const now = new Date();
      const optionsDate = { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' };
      setCurrentDateStr(now.toLocaleDateString('en-GB', optionsDate));
      setCurrentTimeStr(now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true }));
    }
    updateClock();
    const interval = setInterval(updateClock, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <section className={styles.heroSection} aria-label="Dashboard Overview">
      <div className={styles.heroLeft}>
        <h1 className={styles.greetingTitle}>
          Welcome, Inspector <span className={styles.waveHand} role="img" aria-label="waving hand">👋</span>
        </h1>
        <p className={styles.greetingSubtitle}>
          Verify travel documents quickly, securely and accurately using AI, biometrics and forensic analysis.
        </p>
      </div>

      <div className={styles.heroRight}>
        {/* Date & Time Widget */}
        <div className={styles.timeCard}>
          <div className={styles.calendarIconBox} aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
            </svg>
          </div>
          <div className={styles.timeTextGroup}>
            <span className={styles.timeDate}>{currentDateStr}</span>
            <span className={styles.timeClock}>{currentTimeStr}</span>
          </div>
        </div>

        {/* KPI 1: Verified Today (Blue) */}
        <div className={`${styles.kpiCard} ${styles.kpiBlue}`}>
          <div className={styles.kpiIconBox}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
            </svg>
          </div>
          <div className={styles.kpiContent}>
            <span className={styles.kpiValue}>128</span>
            <span className={styles.kpiLabel}>Verified Today</span>
          </div>
        </div>

        {/* KPI 2: Clear (Green) */}
        <div className={`${styles.kpiCard} ${styles.kpiGreen}`}>
          <div className={styles.kpiIconBox}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <polyline points="9 12 11 14 15 10" />
            </svg>
          </div>
          <div className={styles.kpiContent}>
            <span className={styles.kpiValue}>122</span>
            <span className={styles.kpiLabel}>Clear</span>
          </div>
        </div>

        {/* KPI 3: Needs Review (Amber) */}
        <div className={`${styles.kpiCard} ${styles.kpiAmber}`}>
          <div className={styles.kpiIconBox}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>
          <div className={styles.kpiContent}>
            <span className={styles.kpiValue}>5</span>
            <span className={styles.kpiLabel}>Needs Review</span>
          </div>
        </div>

        {/* KPI 4: High Risk (Red) */}
        <div className={`${styles.kpiCard} ${styles.kpiRed}`}>
          <div className={styles.kpiIconBox}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
          </div>
          <div className={styles.kpiContent}>
            <span className={styles.kpiValue}>1</span>
            <span className={styles.kpiLabel}>High Risk</span>
          </div>
        </div>
      </div>
    </section>
  );
}
