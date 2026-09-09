/**
 * DocumentSelector.jsx
 *
 * Horizontal segmented navigation bar for selecting the active document type.
 * Switching tabs dispatches SELECT_DOCUMENT_TYPE, which resets the full session.
 *
 * Features dedicated document iconography and technical standard badges.
 */
import { useVerification } from '../../state/verification/useVerification.js';
import { DOCUMENT_TYPE_ORDER, DOCUMENT_PROFILES, DOCUMENT_TYPES } from '../../config/documentProfiles.js';
import styles from './DocumentSelector.module.css';

function getDocIcon(docType) {
  switch (docType) {
    case DOCUMENT_TYPES.PASSPORT:
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="4" y="2" width="16" height="20" rx="2" />
          <circle cx="12" cy="10" r="3" />
          <path d="M7 17h10" />
        </svg>
      );
    case DOCUMENT_TYPES.VISA:
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
          <circle cx="12" cy="12" r="9" />
        </svg>
      );
    case DOCUMENT_TYPES.DRIVING_LICENSE:
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="2" y="4" width="20" height="16" rx="3" />
          <circle cx="8" cy="12" r="2.5" />
          <line x1="14" y1="10" x2="19" y2="10" />
          <line x1="14" y1="14" x2="18" y2="14" />
        </svg>
      );
    case DOCUMENT_TYPES.AADHAAR:
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <circle cx="8" cy="11" r="2.5" />
          <line x1="13" y1="9" x2="18" y2="9" />
          <line x1="13" y1="13" x2="17" y2="13" />
          <line x1="6" y1="16" x2="18" y2="16" />
        </svg>
      );
    case DOCUMENT_TYPES.VOTER_ID:
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M9 11l3 3L22 4" />
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
        </svg>
      );
    case DOCUMENT_TYPES.PAN_CARD:
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="2" y="4" width="20" height="16" rx="2" />
          <line x1="2" y1="9" x2="22" y2="9" />
          <line x1="6" y1="14" x2="12" y2="14" />
        </svg>
      );
    case DOCUMENT_TYPES.BORDER_PERMIT:
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          <path d="M9 12l2 2 4-4" />
        </svg>
      );
    default:
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        </svg>
      );
  }
}

function getStandardTag(docType) {
  switch (docType) {
    case DOCUMENT_TYPES.PASSPORT:       return 'TD3';
    case DOCUMENT_TYPES.VISA:           return 'MRV';
    case DOCUMENT_TYPES.DRIVING_LICENSE:return 'DL';
    case DOCUMENT_TYPES.AADHAAR:        return 'UIDAI';
    case DOCUMENT_TYPES.VOTER_ID:       return 'EPIC';
    case DOCUMENT_TYPES.PAN_CARD:       return 'PAN';
    case DOCUMENT_TYPES.BORDER_PERMIT:  return 'BPT';
    default: return '';
  }
}

export default function DocumentSelector() {
  const { session, actions } = useVerification();

  function handleSelect(docType) {
    const profile = DOCUMENT_PROFILES[docType];
    if (!profile || profile.status !== 'available') return;
    if (docType === session.documentType) return;
    actions.selectDocumentType(docType);
  }

  return (
    <nav className={styles.nav} aria-label="Document type selection">
      <div className={styles.container}>
        <ol className={styles.tabList} role="tablist">
          {DOCUMENT_TYPE_ORDER.map((docType) => {
            const profile = DOCUMENT_PROFILES[docType];
            const isActive = session.documentType === docType;
            const isAvailable = profile.status === 'available';
            const standardTag = getStandardTag(docType);

            return (
              <li key={docType} role="presentation" className={styles.tabItem}>
                <button
                  id={`tab-${docType}`}
                  role="tab"
                  aria-selected={isActive}
                  aria-controls={`tabpanel-${docType}`}
                  aria-disabled={!isAvailable}
                  className={`${styles.tab} ${isActive ? styles.active : ''} ${!isAvailable ? styles.disabled : ''}`}
                  onClick={() => handleSelect(docType)}
                  type="button"
                  title={!isAvailable ? `${profile.label} verification coming soon` : undefined}
                >
                  <span className={styles.iconWrapper} aria-hidden="true">
                    {getDocIcon(docType)}
                  </span>
                  <span className={styles.tabLabel}>{profile.label}</span>
                  {!isAvailable ? (
                    <span className={styles.comingSoonTag} aria-hidden="true">
                      Soon
                    </span>
                  ) : standardTag ? (
                    <span className={styles.standardTag} aria-hidden="true">
                      {standardTag}
                    </span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ol>
      </div>
    </nav>
  );
}

