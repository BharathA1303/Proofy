/**
 * TravelerInformation.jsx
 *
 * Displays extracted traveler identity dossier.
 *
 * Layout:
 *   - Biometric portrait reticle placeholder
 *   - Structured identity grid with monospace credentials
 *   - Dedicated ICAO Doc 9303 Machine Readable Zone (MRZ) strip
 *
 * Fields shown adapt dynamically to active document profile.
 */
import { useVerification } from '../../state/verification/useVerification.js';
import { getProfile } from '../../config/documentProfiles.js';
import SectionHeader from '../common/SectionHeader.jsx';
import styles from './TravelerInformation.module.css';

export default function TravelerInformation() {
  const { session } = useVerification();
  const profile = getProfile(session.documentType);

  // Defensively filter traveler fields from profile
  const allFields = Array.isArray(profile?.travelerFields) ? profile.travelerFields.filter(Boolean) : [];
  const regularFields = allFields.filter((f) => f && f.key && f.key !== 'mrz');
  const mrzValue = session.traveler?.mrz;
  const hasMRZ = allFields.some((f) => f && f.key === 'mrz') || Boolean(mrzValue);

  return (
    <div className={styles.section} aria-label="Traveler identity dossier">
      <SectionHeader
        title="Traveler Identity Dossier"
        subtitle="Extracted credential records & biometrics"
        level={3}
      />

      {/* Identity Card Header: Clean Photo Frame + Core ID */}
      <div className={styles.dossierTop}>
        <div className={styles.photoFrame} aria-label="Traveler photo placeholder">
          <svg
            className={styles.portraitIcon}
            width="36" height="36" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
            strokeLinejoin="round" aria-hidden="true"
          >
            <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
          <span className={styles.photoLabel}>Photo ID</span>
        </div>

        <div className={styles.primaryIdentity}>
          <div className={styles.primaryItem}>
            <span className={styles.fieldLabel}>FULL NAME</span>
            <span className={`${styles.primaryVal} ${!session.traveler?.name ? styles.empty : ''}`}>
              {session.traveler?.name || '— — — — — —'}
            </span>
          </div>

          <div className={styles.docNumRow}>
            <div className={styles.primaryItem}>
              <span className={styles.fieldLabel}>DOCUMENT NUMBER</span>
              <span className={`${styles.docNumVal} ${!session.traveler?.docNumber ? styles.empty : ''}`}>
                {session.traveler?.docNumber || '— — — — —'}
              </span>
            </div>
            <div className={styles.primaryItem}>
              <span className={styles.fieldLabel}>NATIONALITY</span>
              <span className={`${styles.primaryVal} ${!session.traveler?.nationality ? styles.empty : ''}`}>
                {session.traveler?.nationality || '— — —'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Field Grid for remaining parameters */}
      <dl className={styles.fieldGrid}>
        {regularFields
          .filter((f) => f && f.key && !['name', 'docNumber', 'nationality'].includes(f.key))
          .map((field) => {
            const rawValue = session.traveler?.[field.key];
            const isEmpty = rawValue === null || rawValue === undefined || String(rawValue).trim() === '';

            return (
              <div key={field.key} className={styles.fieldItem}>
                <dt className={styles.fieldLabel}>{field.label || field.key}</dt>
                <dd className={`${styles.fieldValue} ${isEmpty ? styles.empty : ''}`}>
                  {isEmpty ? '—' : String(rawValue)}
                </dd>
              </div>
            );
          })}
      </dl>

      {/* Machine Readable Zone (MRZ) Strip (Only if applicable to profile or detected) */}
      {hasMRZ && (
        <div className={styles.mrzContainer}>
          <div className={styles.mrzHeader}>
            <span className={styles.mrzTitle}>MACHINE READABLE ZONE (ICAO DOC 9303)</span>
            <span className={styles.mrzStandard}>OCR-B OPTICAL STRIP</span>
          </div>
          <div className={styles.mrzBox}>
            {mrzValue ? (
              <pre className={styles.mrzText}>{mrzValue}</pre>
            ) : (
              <div className={styles.mrzPlaceholder}>
                <code>P&lt;UTO------------------------------------------</code>
                <code>--------------------------------------------</code>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

