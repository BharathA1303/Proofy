/**
 * ForensicEvidence.jsx
 *
 * Displays forensic analysis evidence in a collapsible terminal drawer.
 * In standby / empty: shows an authentic forensic baseline placeholder.
 * When evidence exists (populated by backend): renders each item with severity flags.
 */
import { useState } from 'react';
import { useVerification } from '../../state/verification/useVerification.js';
import SectionHeader from '../common/SectionHeader.jsx';
import styles from './ForensicEvidence.module.css';

/**
 * @param {{ item: { type: string, label: string, severity: string, detail: string } }} props
 */
function EvidenceItem({ item }) {
  const [expanded, setExpanded] = useState(false);

  const severityClass = {
    info:     styles.info,
    warning:  styles.warning,
    critical: styles.critical,
  }[item.severity] ?? styles.info;

  return (
    <li className={`${styles.item} ${severityClass}`}>
      <button
        className={styles.itemHeader}
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        type="button"
      >
        <span className={styles.severityTag}>{item.severity?.toUpperCase() || 'INFO'}</span>
        <span className={styles.itemLabel}>{item.label}</span>
        <span className={styles.itemType}>{item.type}</span>
        <span className={`${styles.chevron} ${expanded ? styles.chevronOpen : ''}`} aria-hidden="true">
          ›
        </span>
      </button>

      {expanded && item.detail && (
        <div className={styles.itemDetail}>
          <p>{item.detail}</p>
        </div>
      )}
    </li>
  );
}

export default function ForensicEvidence() {
  const { session } = useVerification();
  const { forensicEvidence } = session;
  const [panelOpen, setPanelOpen] = useState(false);

  const hasEvidence = forensicEvidence.length > 0;

  return (
    <div className={styles.section} aria-label="Forensic evidence and audit">
      <button
        className={styles.panelToggle}
        onClick={() => setPanelOpen((v) => !v)}
        aria-expanded={panelOpen}
        type="button"
      >
        <div className={styles.headerContent}>
          <div className={styles.titleGroup}>
            <SectionHeader
              title="Forensic Audit Telemetry & Artifacts"
              subtitle={hasEvidence ? `${forensicEvidence.length} anomaly artifact${forensicEvidence.length !== 1 ? 's' : ''} detected` : 'Module 3 Forensic Pipeline · Baseline Standby'}
              level={3}
            />
          </div>
          <div className={styles.toggleRight}>
            <span className={styles.countBadge}>
              {hasEvidence ? `${forensicEvidence.length} FINDINGS` : '0 FINDINGS'}
            </span>
            <span className={`${styles.toggleChevron} ${panelOpen ? styles.toggleOpen : ''}`} aria-hidden="true">
              ▾
            </span>
          </div>
        </div>
      </button>

      {panelOpen && (
        <div className={styles.content}>
          {!hasEvidence ? (
            <div className={styles.emptyState}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                <path d="m9 12 2 2 4-4" />
              </svg>
              <p className={styles.emptyText}>
                {session.result === null
                  ? 'Forensic image tampering, ELA, and metadata audit results will populate upon executing the verification pipeline.'
                  : 'No tampering artifacts or forensic anomalies detected for this credential.'}
              </p>
            </div>
          ) : (
            <ul className={styles.evidenceList} aria-label="Forensic findings">
              {forensicEvidence.map((item, i) => (
                <EvidenceItem key={item.id ?? i} item={item} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

