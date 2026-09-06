/**
 * PreviewAndExtractedCard.jsx
 *
 * Right column of the 3-column workspace matching the exact reference image:
 * - Top Box: Document Preview with expand icon and image view
 * - Bottom Box: Extracted Information with standby text or extracted attribute grid
 */
import { useEffect, useState } from 'react';
import { useVerification } from '../../state/verification/useVerification.js';
import styles from './PreviewAndExtractedCard.module.css';

export default function PreviewAndExtractedCard() {
  const { session } = useVerification();
  const [previewUrl, setPreviewUrl] = useState(null);
  const [showFullPreview, setShowFullPreview] = useState(false);

  const traveler = session.traveler || {};
  const hasExtractedData = Boolean(
    traveler.name || traveler.docNumber || traveler.nationality || traveler.dob
  );

  // Generate real object URL whenever session.file changes
  useEffect(() => {
    if (!session.file) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(session.file);
    setPreviewUrl(url);
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [session.file]);

  return (
    <div className={styles.rightColumnContainer}>
      {/* ── Top Box: Document Preview ── */}
      <div className={styles.cardBox}>
        <div className={styles.boxHeader}>
          <div className={styles.headerTitleGroup}>
            <div className={styles.headerIconBox} aria-hidden="true">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
            </div>
            <h2 className={styles.boxTitle}>Document Preview</h2>
          </div>
          <button
            type="button"
            className={styles.expandBtn}
            onClick={() => setShowFullPreview(true)}
            title="Expand document preview"
            aria-label="Expand document preview"
            disabled={!previewUrl}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 3 21 3 21 9" />
              <polyline points="9 21 3 21 3 15" />
              <line x1="21" y1="3" x2="14" y2="10" />
              <line x1="3" y1="21" x2="10" y2="14" />
            </svg>
          </button>
        </div>

        <div className={styles.previewContentArea}>
          {previewUrl ? (
            <div className={styles.imagePreviewWrapper}>
              <img
                src={previewUrl}
                alt="Document Preview Scan"
                className={styles.documentImage}
              />
            </div>
          ) : (
            <div className={styles.emptyPreviewState}>
              <div className={styles.placeholderIconBox} aria-hidden="true">
                <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                  <circle cx="8.5" cy="8.5" r="1.5" />
                  <polyline points="21 15 16 10 5 21" />
                </svg>
              </div>
              <p className={styles.emptyText}>Document preview will appear here after upload</p>
            </div>
          )}
        </div>
      </div>

      {/* ── Bottom Box: Extracted Information ── */}
      <div className={styles.cardBox}>
        <div className={styles.boxHeader}>
          <div className={styles.headerTitleGroup}>
            <div className={styles.headerIconBox} aria-hidden="true">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
                <polyline points="10 9 9 9 8 9" />
              </svg>
            </div>
            <h2 className={styles.boxTitle}>Extracted Information</h2>
          </div>
        </div>

        <div className={styles.extractedContentArea}>
          {!hasExtractedData ? (
            <div className={styles.emptyExtractedState}>
              <p className={styles.emptyText}>Fields will be displayed here after OCR extraction</p>
            </div>
          ) : (
            <div className={styles.fieldsGrid}>
              {traveler.name && (
                <div className={styles.fieldItem}>
                  <span className={styles.fieldLabel}>FULL NAME</span>
                  <span className={styles.fieldValue}>{traveler.name}</span>
                </div>
              )}
              {traveler.docNumber && (
                <div className={styles.fieldItem}>
                  <span className={styles.fieldLabel}>DOCUMENT NUMBER</span>
                  <span className={styles.fieldValueHighlight}>{traveler.docNumber}</span>
                </div>
              )}
              {traveler.nationality && (
                <div className={styles.fieldItem}>
                  <span className={styles.fieldLabel}>NATIONALITY</span>
                  <span className={styles.fieldValue}>{traveler.nationality}</span>
                </div>
              )}
              {traveler.dob && (
                <div className={styles.fieldItem}>
                  <span className={styles.fieldLabel}>DATE OF BIRTH</span>
                  <span className={styles.fieldValue}>{traveler.dob}</span>
                </div>
              )}
              {traveler.expiry && (
                <div className={styles.fieldItem}>
                  <span className={styles.fieldLabel}>EXPIRY DATE</span>
                  <span className={styles.fieldValue}>{traveler.expiry}</span>
                </div>
              )}
              {traveler.gender && (
                <div className={styles.fieldItem}>
                  <span className={styles.fieldLabel}>GENDER</span>
                  <span className={styles.fieldValue}>{traveler.gender}</span>
                </div>
              )}
              {traveler.authority && (
                <div className={styles.fieldItem}>
                  <span className={styles.fieldLabel}>ISSUING AUTHORITY</span>
                  <span className={styles.fieldValue}>{traveler.authority}</span>
                </div>
              )}
              {traveler.mrz && (
                <div className={`${styles.fieldItem} ${styles.fullWidth}`}>
                  <span className={styles.fieldLabel}>MACHINE READABLE ZONE (MRZ)</span>
                  <pre className={styles.mrzCodeBlock}>{traveler.mrz}</pre>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Fullscreen Preview Modal */}
      {showFullPreview && previewUrl && (
        <div className={styles.modalBackdrop} onClick={() => setShowFullPreview(false)}>
          <div className={styles.modalBox} onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              className={styles.closeModalBtn}
              onClick={() => setShowFullPreview(false)}
            >
              ✕
            </button>
            <img src={previewUrl} alt="Expanded Document Preview" className={styles.modalImage} />
          </div>
        </div>
      )}
    </div>
  );
}
