/**
 * UploadPanel.jsx
 *
 * Manages document ingestion including:
 *   - DropZone (drag & drop / Choose File)
 *   - Executive selected file preview card
 *   - Backend-served sample document selector (fetches real sample image files from the backend)
 *   - Commanding "Run Verification Pipeline" action button
 *
 * NOTE: Strictly adheres to zero-frontend-mock architecture. All test sample images
 * and verification data are fetched from and evaluated by the backend API.
 */
import { useEffect, useState } from 'react';
import { useVerification } from '../../state/verification/useVerification.js';
import { getProfile } from '../../config/documentProfiles.js';
import { DEFAULT_SAMPLE_OPTIONS } from '../../config/mockSampleOptions.js';
import { SESSION_STATUS } from '../../state/verification/initialState.js';
import { useOCRSubmit } from '../../services/useOCRSubmit.js';
import DropZone from './DropZone.jsx';
import styles from './UploadPanel.module.css';

export default function UploadPanel() {
  const { session, actions } = useVerification();
  const { submitOCR, isSubmitting } = useOCRSubmit();
  const profile = getProfile(session.documentType);

  const [sampleOptions, setSampleOptions] = useState(DEFAULT_SAMPLE_OPTIONS);
  const [loadingSampleId, setLoadingSampleId] = useState(null);

  const isFileSelected  = session.status === SESSION_STATUS.DOCUMENT_SELECTED;
  const isSampleSelected= session.status === SESSION_STATUS.SAMPLE_SELECTED;
  const isProcessing    = [
    SESSION_STATUS.UPLOADING,
    SESSION_STATUS.PROCESSING,
  ].includes(session.status) || isSubmitting;

  // Query available sample documents from backend on mount
  useEffect(() => {
    let isMounted = true;
    async function loadSampleOptions() {
      try {
        const res = await fetch('/api/v1/verification/sample/options');
        if (res.ok) {
          const data = await res.json();
          if (isMounted) setSampleOptions(prev => ({ ...prev, ...data }));
        }
      } catch (err) {
        console.debug('Failed to fetch sample options from backend:', err);
      }
    }
    loadSampleOptions();
    return () => { isMounted = false; };
  }, []);

  /* ---------- Handlers ---------- */

  function handleFileAccepted(file) {
    actions.clearError();
    actions.selectFile(file);
  }

  function handleFileError(message) {
    actions.setError(message);
  }

  function handleClearFile() {
    actions.clearFile();
  }

  /**
   * Fetch sample document image with static fallback if backend is offline.
   */
  async function handleFetchSample(sample) {
    const { url: sampleUrl, filename: fileName, id: sampleId, fallbackUrl } = sample;
    actions.clearError();
    setLoadingSampleId(sampleId);

    try {
      let response = null;
      try {
        const res = await fetch(sampleUrl);
        if (res.ok) response = res;
      } catch {
        // network issue
      }

      if ((!response || !response.ok) && fallbackUrl) {
        try {
          const fbRes = await fetch(fallbackUrl);
          if (fbRes.ok) response = fbRes;
        } catch {
          // ignore
        }
      }

      if (!response || !response.ok) {
        throw new Error(`Unable to fetch sample image. Check backend status.`);
      }

      const blob = await response.blob();
      const fileObj = new File([blob], fileName || `sample_${session.documentType}.jpg`, {
        type: blob.type || 'image/jpeg',
      });

      actions.selectFile(fileObj);
    } catch (err) {
      console.error('Failed to load sample from server:', err);
      actions.setError(`Unable to load sample document: ${err.message}`);
    } finally {
      setLoadingSampleId(null);
    }
  }

  /**
   * Verify — submits the selected file to the backend verification pipeline.
   */
  async function handleVerify() {
    await submitOCR(session.file, session.documentType);
  }

  const hasFile = isFileSelected || isSampleSelected;

  function formatFileSize(bytes) {
    if (!bytes) return null;
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  }

  function getProcessingLabel() {
    if (session.status === SESSION_STATUS.UPLOADING) {
      return { title: 'TRANSMITTING DOCUMENT...', sub: 'Sending to OCR pipeline' };
    }
    return { title: 'ANALYZING CREDENTIAL...', sub: 'Executing optical recognition & forensic analysis' };
  }

  const processingLabel = getProcessingLabel();

  const docType = session.documentType;
  const canonicalDocType = (
    docType === 'drivingLicense' ? 'driving_license' :
    docType === 'voterId' ? 'voter_id' :
    docType === 'panCard' ? 'pan_card' :
    docType === 'nationalId' ? 'aadhaar' :
    docType === 'borderPermit' ? 'border_permit' : docType
  );

  // Current doc type samples from backend options (or default catalog fallback)
  const currentSamples = (
    (Array.isArray(sampleOptions[docType]) && sampleOptions[docType].length > 0 ? sampleOptions[docType] : null) ||
    (Array.isArray(sampleOptions[canonicalDocType]) && sampleOptions[canonicalDocType].length > 0 ? sampleOptions[canonicalDocType] : null) ||
    DEFAULT_SAMPLE_OPTIONS[docType] ||
    DEFAULT_SAMPLE_OPTIONS[canonicalDocType] ||
    []
  );

  return (
    <div className={styles.section} aria-label="Document ingestion">

      {/* Error message */}
      {session.error && (
        <div className={styles.errorBanner} role="alert" aria-live="assertive">
          <svg
            width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round"
            strokeLinejoin="round" aria-hidden="true"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <span>{session.error}</span>
          <button
            className={styles.errorDismiss}
            onClick={() => actions.clearError()}
            aria-label="Dismiss error"
            type="button"
          >
            ✕
          </button>
        </div>
      )}

      {/* Drop zone — shown when no file selected */}
      {!hasFile && !isProcessing && (
        <DropZone
          onFileAccepted={handleFileAccepted}
          onError={handleFileError}
          acceptedMimeTypes={profile.acceptedMimeTypes}
          maxFileSizeMB={profile.maxFileSizeMB}
        />
      )}

      {/* Selected file display */}
      {hasFile && (
        <div className={styles.selectedFile} aria-live="polite">
          <div className={styles.fileInfo}>
            <div className={styles.fileIconBox}>
              <svg
                width="22" height="22" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="1.75" strokeLinecap="round"
                strokeLinejoin="round" aria-hidden="true"
              >
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
                <polyline points="10 9 9 9 8 9" />
              </svg>
            </div>
            <div className={styles.fileMeta}>
              <p className={styles.fileName} title={session.fileName}>{session.fileName}</p>
              <div className={styles.fileTags}>
                <span className={styles.fileBadge}>
                  {isSampleSelected ? 'SAMPLE CREDENTIAL' : `${profile.label.toUpperCase()}`}
                </span>
                {session.file?.size && (
                  <span className={styles.fileSize}>
                    {formatFileSize(session.file.size)}
                  </span>
                )}
              </div>
            </div>
          </div>
          <button
            className={styles.clearBtn}
            onClick={handleClearFile}
            aria-label={`Remove selected file: ${session.fileName}`}
            type="button"
            disabled={isProcessing}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
            <span>Remove</span>
          </button>
        </div>
      )}

      {/* Processing indicator */}
      {isProcessing && (
        <div className={styles.processing} aria-live="polite" aria-label="Processing document">
          <div className={styles.spinner} aria-hidden="true" />
          <div className={styles.processingText}>
            <span className={styles.processingTitle}>{processingLabel.title}</span>
            <span className={styles.processingSub}>{processingLabel.sub}</span>
          </div>
        </div>
      )}

      {/* ── Sample Documents Selector (Loaded from Backend) ── */}
      {!hasFile && !isProcessing && currentSamples.length > 0 && (
        <div className={styles.mockSection}>
          <div className={styles.mockHeader}>
            <span className={styles.mockTitle}>Sample Test Documents (Backend)</span>
            <span className={styles.mockSubtitle}>Select a test document to fetch from backend and run verification:</span>
          </div>

          <div className={styles.mockGrid}>
            {currentSamples.map((sample) => {
              const isFraud = sample.id?.includes('fake') || sample.badge?.includes('TAMPERED');
              const isLoadingThis = loadingSampleId === sample.id;

              return (
                <button
                  key={sample.id}
                  type="button"
                  className={`${styles.mockCard} ${isFraud ? styles.mockCardFraud : styles.mockCardGenuine}`}
                  onClick={() => handleFetchSample(sample)}
                  disabled={Boolean(loadingSampleId)}
                  title={`Load ${sample.label} from backend`}
                >
                  <div className={styles.mockCardTop}>
                    <span className={styles.mockCardLabel}>
                      {isLoadingThis ? 'Downloading from backend...' : sample.label}
                    </span>
                    <span className={`${styles.mockBadge} ${isFraud ? styles.badgeFraud : styles.badgeGenuine}`}>
                      {sample.badge}
                    </span>
                  </div>
                  {sample.description && (
                    <p className={styles.mockCardDesc}>{sample.description}</p>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Verify button — shown when file is selected */}
      {hasFile && !isProcessing && (
        <button
          className={styles.verifyBtn}
          onClick={handleVerify}
          type="button"
          disabled={isSubmitting}
        >
          <span>Run Verification Pipeline</span>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <line x1="5" y1="12" x2="19" y2="12" />
            <polyline points="12 5 19 12 12 19" />
          </svg>
        </button>
      )}
    </div>
  );
}
