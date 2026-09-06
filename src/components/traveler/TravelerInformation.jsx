/**
 * TravelerInformation.jsx
 *
 * Displays extracted traveler identity dossier.
 * Clean, distraction-free layout:
 *   - Empty state: Clean placeholder when standby (no ugly dashes or dummy MRZ).
 *   - Populated state: Executive identity card with portrait badge, primary credentials,
 *     and structured attribute grid.
 */
import { useState } from 'react';
import { useVerification } from '../../state/verification/useVerification.js';
import { getProfile } from '../../config/documentProfiles.js';
import styles from './TravelerInformation.module.css';

export default function TravelerInformation() {
  const { session } = useVerification();
  const profile = getProfile(session.documentType);
  const [showRawMRZ, setShowRawMRZ] = useState(false);

  const traveler = session.traveler || {};
  const hasExtractedData = Boolean(traveler.name || traveler.docNumber || traveler.nationality || traveler.dob);

  // Filter regular fields from profile
  const allFields = Array.isArray(profile?.travelerFields) ? profile.travelerFields.filter(Boolean) : [];
  const regularFields = allFields.filter((f) => f && f.key && !['name', 'docNumber', 'nationality', 'mrz'].includes(f.key));
  const mrzValue = traveler.mrz;

  return (
    <div className={styles.container} aria-label="Traveler Identity Dossier">
      <div className={styles.cardHeader}>
        <div className={styles.headerTitleGroup}>
          <span className={styles.cardTitle}>Traveler Identity Record</span>
          <span className={styles.cardTag}>{profile.label} Verified Dossier</span>
        </div>
        {hasExtractedData && (
          <span className={styles.extractedBadge}>OCR Extracted</span>
        )}
      </div>

      {/* Standby State: Clean & Distraction-free */}
      {!hasExtractedData ? (
        <div className={styles.emptyState}>
          <div className={styles.emptyIconBox} aria-hidden="true">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
          </div>
          <p className={styles.emptyTitle}>Awaiting Credential Intake</p>
          <p className={styles.emptyDesc}>
            Upload a document to extract traveler identity details, document numbers, and optical strips.
          </p>
        </div>
      ) : (
        <div className={styles.dossierContent}>
          {/* Identity Card Header: Photo Frame + Primary Credentials */}
          <div className={styles.identityHeader}>
            <div className={styles.photoFrame} aria-label="Traveler photo ID">
              <svg className={styles.portraitIcon} width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
              <span className={styles.photoTag}>PORTRAIT</span>
            </div>

            <div className={styles.primaryFields}>
              <div className={styles.nameRow}>
                <span className={styles.fieldLabel}>FULL NAME</span>
                <span className={styles.fullNameVal}>{traveler.name || 'UNSPECIFIED'}</span>
              </div>

              <div className={styles.metaRow}>
                <div className={styles.metaItem}>
                  <span className={styles.fieldLabel}>DOCUMENT NO.</span>
                  <span className={styles.docNumberBadge}>{traveler.docNumber || '—'}</span>
                </div>
                <div className={styles.metaItem}>
                  <span className={styles.fieldLabel}>NATIONALITY</span>
                  <span className={styles.nationalityBadge}>{traveler.nationality || '—'}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Secondary Parameters Grid */}
          <div className={styles.fieldGrid}>
            {regularFields.map((field) => {
              const value = traveler[field.key];
              if (!value || String(value).trim() === '') return null;

              return (
                <div key={field.key} className={styles.fieldItem}>
                  <span className={styles.gridLabel}>{field.label}</span>
                  <span className={styles.gridValue}>{String(value)}</span>
                </div>
              );
            })}
          </div>

          {/* Collapsible MRZ Strip */}
          {mrzValue && (
            <div className={styles.mrzSection}>
              <button
                type="button"
                className={styles.mrzToggleBtn}
                onClick={() => setShowRawMRZ((prev) => !prev)}
                aria-expanded={showRawMRZ}
              >
                <span className={styles.mrzBtnLabel}>
                  {showRawMRZ ? 'Hide Optical Strip (MRZ)' : 'View Machine Readable Zone (MRZ)'}
                </span>
                <svg
                  className={`${styles.chevron} ${showRawMRZ ? styles.chevronOpen : ''}`}
                  width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                >
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </button>

              {showRawMRZ && (
                <div className={styles.mrzBox}>
                  <pre className={styles.mrzText}>{mrzValue}</pre>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
