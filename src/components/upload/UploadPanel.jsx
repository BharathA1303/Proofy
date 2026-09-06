/**
 * UploadPanel.jsx
 *
 * Manages document ingestion including:
 *   - DropZone (drag & drop / Choose File)
 *   - Executive selected file preview card
 *   - Quick Sample document trigger (explicit user action)
 *   - Commanding "Run Verification" action button
 *
 * Adheres strictly to decoupled state architecture: triggers action via
 * useVerification actions without direct mutation.
 *
 * Phase 1: Passport OCR is wired via useOCRSubmit.
 * For other document types, a clear "not yet implemented" message is shown.
 */
import { useVerification } from '../../state/verification/useVerification.js';
import { getProfile } from '../../config/documentProfiles.js';
import { DOCUMENT_TYPES } from '../../config/documentProfiles.js';
import { SESSION_STATUS } from '../../state/verification/initialState.js';
import { useOCRSubmit } from '../../services/useOCRSubmit.js';
import DropZone from './DropZone.jsx';
import SectionHeader from '../common/SectionHeader.jsx';
import styles from './UploadPanel.module.css';

export default function UploadPanel() {
  const { session, actions } = useVerification();
  const { submitOCR, isSubmitting } = useOCRSubmit();
  const profile = getProfile(session.documentType);

  const isFileSelected  = session.status === SESSION_STATUS.DOCUMENT_SELECTED;
  const isSampleSelected= session.status === SESSION_STATUS.SAMPLE_SELECTED;
  const isProcessing    = [
    SESSION_STATUS.UPLOADING,
    SESSION_STATUS.PROCESSING,
  ].includes(session.status) || isSubmitting;

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
   * Sample Format — loads the synthetic sample asset as a real File object.
   * For Passport: fetches the synthetic test image from the backend tests directory
   * (served via the Vite dev proxy or a static file server).
   * For other document types: sets a sample_selected state (no real OCR).
   */
  async function handleLoadSample() {
    actions.clearError();

    if (session.documentType === DOCUMENT_TYPES.PASSPORT) {
      // Fetch the synthetic test passport image as a real File so it can go
      // through the full OCR pipeline when "Verify Document" is clicked.
      try {
        const sampleUrl = '/api/v1/verification/sample/passport';
        const response = await fetch(sampleUrl);

        if (response.ok) {
          const blob = await response.blob();
          const syntheticFile = new File([blob], 'Sample_Passport.jpg', { type: 'image/jpeg' });
          actions.selectFile(syntheticFile);
          return;
        }
      } catch {
        // Fall through to basic selectSample if the sample endpoint isn't available
      }
    } else if (session.documentType === DOCUMENT_TYPES.VISA) {
      // Fetch the synthetic test visa image as a real File
      try {
        const sampleUrl = '/api/v1/verification/sample/visa';
        const response = await fetch(sampleUrl);

        if (response.ok) {
          const blob = await response.blob();
          const syntheticFile = new File([blob], 'Sample_Visa.jpg', { type: 'image/jpeg' });
          actions.selectFile(syntheticFile);
          return;
        }
      } catch {
        // Fall through to basic selectSample if the sample endpoint isn't available
      }
    } else if (session.documentType === DOCUMENT_TYPES.DRIVING_LICENSE) {
      // Fetch the synthetic test driving license image as a real File
      try {
        const sampleUrl = '/api/v1/verification/sample/driving_license';
        const response = await fetch(sampleUrl);

        if (response.ok) {
          const blob = await response.blob();
          const syntheticFile = new File([blob], 'Sample_Driving_License.jpg', { type: 'image/jpeg' });
          actions.selectFile(syntheticFile);
          return;
        }
      } catch {
        // Fall through to basic selectSample if the sample endpoint isn't available
      }
    } else if (session.documentType === DOCUMENT_TYPES.NATIONAL_ID) {
      // Fetch the synthetic test national id image as a real File
      try {
        const sampleUrl = '/api/v1/verification/sample/national_id';
        const response = await fetch(sampleUrl);

        if (response.ok) {
          const blob = await response.blob();
          const syntheticFile = new File([blob], 'Sample_National_ID.jpg', { type: 'image/jpeg' });
          actions.selectFile(syntheticFile);
          return;
        }
      } catch {
        // Fall through to basic selectSample if the sample endpoint isn't available
      }
    } else if (session.documentType === DOCUMENT_TYPES.BORDER_PERMIT) {
      // Fetch the synthetic test border permit image as a real File
      try {
        const sampleUrl = '/api/v1/verification/sample/border_permit';
        const response = await fetch(sampleUrl);

        if (response.ok) {
          const blob = await response.blob();
          const syntheticFile = new File([blob], 'Sample_Border_Permit.jpg', { type: 'image/jpeg' });
          actions.selectFile(syntheticFile);
          return;
        }
      } catch {
        // Fall through to basic selectSample if the sample endpoint isn't available
      }
    }

    // Default: mark as sample_selected (no OCR will run until real file submitted)
    actions.selectSample(
      `Sample_${profile.label.replace(/\s+/g, '_')}.jpg`,
      `sample_${session.documentType}`,
    );
  }

  /**
   * Verify — Phase 1: submits the selected file to the OCR backend.
   * Transitions: UPLOADING → PROCESSING → COMPLETED / ERROR
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

  /**
   * Determine the processing status label for the spinner indicator.
   */
  function getProcessingLabel() {
    if (session.status === SESSION_STATUS.UPLOADING) {
      return { title: 'TRANSMITTING DOCUMENT...', sub: 'Sending to OCR pipeline' };
    }
    return { title: 'ANALYZING CREDENTIAL...', sub: 'Executing optical text recognition' };
  }

  const processingLabel = getProcessingLabel();

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
                  {isSampleSelected ? 'SAMPLE ARTIFACT' : `${profile.label.toUpperCase()}`}
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

      {/* Sample Format trigger — visible when in standby */}
      {!hasFile && !isProcessing && (
        <div className={styles.sampleRow}>
          <span className={styles.sampleLabel}>Automated test vectors:</span>
          <button
            className={styles.sampleBtn}
            onClick={handleLoadSample}
            type="button"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
            </svg>
            <span>Load Sample {profile.label}</span>
          </button>
        </div>
      )}

      {/* Verify button — shown when file or sample is selected */}
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


