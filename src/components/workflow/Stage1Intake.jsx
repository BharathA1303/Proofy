/**
 * Stage1Intake.jsx
 *
 * Stage 1: Document Type Selection & Intake Upload.
 * Officers select the document standard, upload the physical scan/capture,
 * or select official reference dossiers for inspection.
 */
import { useEffect, useState } from 'react';
import { useVerification } from '../../state/verification/useVerification.js';
import { DOCUMENT_PROFILES, DOCUMENT_TYPES } from '../../config/documentProfiles.js';
import { DEFAULT_SAMPLE_OPTIONS } from '../../config/mockSampleOptions.js';
import { SESSION_STATUS } from '../../state/verification/initialState.js';
import { useOCRSubmit } from '../../services/useOCRSubmit.js';
import DropZone from '../upload/DropZone.jsx';
import styles from './Stage1Intake.module.css';

const DOC_CATEGORIES = [
  {
    type: DOCUMENT_TYPES.PASSPORT,
    label: 'Passport',
    desc: 'International Travel',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <line x1="7" y1="8" x2="17" y2="8" />
        <line x1="7" y1="12" x2="13" y2="12" />
        <circle cx="15" cy="14" r="2" />
      </svg>
    ),
  },
  {
    type: DOCUMENT_TYPES.DRIVING_LICENSE,
    label: 'Driving Licence',
    desc: 'Driver & Transport',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="5" width="20" height="14" rx="2" />
        <circle cx="7" cy="12" r="2.5" />
        <line x1="12" y1="9" x2="19" y2="9" />
        <line x1="12" y1="13" x2="17" y2="13" />
      </svg>
    ),
  },
  {
    type: DOCUMENT_TYPES.AADHAAR,
    label: 'Aadhaar Card',
    desc: 'UIDAI Identity',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
        <circle cx="9" cy="12" r="2.5" />
        <path d="M15 9h3" />
        <path d="M15 12h3" />
        <path d="M15 15h3" />
      </svg>
    ),
  },
  {
    type: DOCUMENT_TYPES.VOTER_ID,
    label: 'Voter ID / EPIC',
    desc: 'Election Commission',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M9 11l3 3L22 4" />
        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
      </svg>
    ),
  },
  {
    type: DOCUMENT_TYPES.PAN_CARD,
    label: 'PAN Card',
    desc: 'Income Tax Dept',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="4" width="20" height="16" rx="2" />
        <line x1="2" y1="10" x2="22" y2="10" />
        <line x1="6" y1="15" x2="12" y2="15" />
      </svg>
    ),
  },
  {
    type: DOCUMENT_TYPES.VISA,
    label: 'Entry Visa',
    desc: 'Travel Visa',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="9" y1="15" x2="15" y2="15" />
      </svg>
    ),
  },
  {
    type: DOCUMENT_TYPES.BORDER_PERMIT,
    label: 'Border Permit',
    desc: 'Border Transit',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
    ),
  },
];


export default function Stage1Intake() {
  const { session, actions } = useVerification();
  const { submitOCR, isSubmitting } = useOCRSubmit();
  const profile = DOCUMENT_PROFILES[session.documentType] || DOCUMENT_PROFILES[DOCUMENT_TYPES.PASSPORT];

  const [sampleOptions, setSampleOptions] = useState(DEFAULT_SAMPLE_OPTIONS);
  const [loadingSampleId, setLoadingSampleId] = useState(null);
  const [filePreviewUrl, setFilePreviewUrl] = useState(null);

  // Catchy live inspection timer states
  const [elapsedMs, setElapsedMs] = useState(0);
  const [isVerifyingWithTimer, setIsVerifyingWithTimer] = useState(false);
  const [completedSeconds, setCompletedSeconds] = useState(null);

  const hasFile = Boolean(session.file);
  const isProcessing = [SESSION_STATUS.UPLOADING, SESSION_STATUS.PROCESSING].includes(session.status) || isSubmitting || isVerifyingWithTimer;

  // Generate thumbnail URL for selected file
  useEffect(() => {
    if (session.file && session.file instanceof File) {
      const url = URL.createObjectURL(session.file);
      setFilePreviewUrl(url);
      return () => URL.revokeObjectURL(url);
    } else {
      setFilePreviewUrl(null);
    }
  }, [session.file]);

  // Load sample options from backend API with automatic retry and window focus re-sync
  useEffect(() => {
    let isMounted = true;
    let retryTimer = null;

    async function loadSamples(attempt = 1) {
      try {
        const res = await fetch('/api/v1/verification/sample/options');
        if (res.ok) {
          const data = await res.json();
          if (isMounted) {
            setSampleOptions((prev) => ({
              ...prev,
              ...data,
            }));
          }
          return;
        }
      } catch (err) {
        console.debug(`Sample options load attempt ${attempt} failed:`, err);
      }

      // If backend was still starting up, retry up to 4 times
      if (isMounted && attempt < 4) {
        retryTimer = setTimeout(() => {
          loadSamples(attempt + 1);
        }, 2000 * attempt);
      }
    }

    loadSamples();

    function handleFocus() {
      loadSamples(1);
    }
    window.addEventListener('focus', handleFocus);

    return () => {
      isMounted = false;
      if (retryTimer) clearTimeout(retryTimer);
      window.removeEventListener('focus', handleFocus);
    };
  }, []);

  const docType = session.documentType;
  const canonicalDocType = (
    docType === 'drivingLicense' ? 'driving_license' :
    docType === 'voterId' ? 'voter_id' :
    docType === 'panCard' ? 'pan_card' :
    docType === 'nationalId' ? 'aadhaar' :
    docType === 'borderPermit' ? 'border_permit' : docType
  );

  // Always resolve to available test vectors (from backend or comprehensive local default catalog)
  const currentSamples = (
    (Array.isArray(sampleOptions[docType]) && sampleOptions[docType].length > 0 ? sampleOptions[docType] : null) ||
    (Array.isArray(sampleOptions[canonicalDocType]) && sampleOptions[canonicalDocType].length > 0 ? sampleOptions[canonicalDocType] : null) ||
    DEFAULT_SAMPLE_OPTIONS[docType] ||
    DEFAULT_SAMPLE_OPTIONS[canonicalDocType] ||
    []
  );

  function handleCategorySelect(type) {
    if (session.documentType !== type) {
      actions.selectDocumentType(type);
    }
  }

  function handleFileAccepted(file) {
    actions.clearError();
    // A manual file upload by default is treated as a real document
    actions.setIsMockVector(false);
    actions.selectFile(file);
  }

  function handleFileError(message) {
    actions.setError(message);
  }

  function handleClearFile() {
    actions.clearFile();
    actions.setIsMockVector(false);
    setFilePreviewUrl(null);
  }

  async function handleLoadSample(sample) {
    const { url: sampleUrl, filename: fileName, id: sampleId, fallbackUrl } = sample;
    actions.clearError();
    setLoadingSampleId(sampleId);
    try {
      let response = null;

      // 1. Try primary URL (backend API endpoint)
      try {
        const res = await fetch(sampleUrl);
        if (res.ok) {
          response = res;
        }
      } catch (primaryErr) {
        console.warn(`Primary sample fetch failed for ${sampleId}, attempting static asset:`, primaryErr);
      }

      // 2. Fall back to static public asset if primary failed
      if ((!response || !response.ok) && fallbackUrl) {
        try {
          const fbRes = await fetch(fallbackUrl);
          if (fbRes.ok) {
            response = fbRes;
          }
        } catch (fallbackErr) {
          console.warn(`Fallback sample fetch failed for ${sampleId}:`, fallbackErr);
        }
      }

      if (!response || !response.ok) {
        throw new Error(
          `Unable to retrieve sample image (${response ? response.status : 'Offline'}). Ensure backend is running.`
        );
      }

      const blob = await response.blob();
      const fileObj = new File([blob], fileName || `sample_${session.documentType}.jpg`, {
        type: blob.type || 'image/jpeg',
      });

      // Special rule: Bharath A's DL is a REAL physical credential that requires real face verification!
      // All other synthetic samples are mock vectors that bypass face verification.
      const isBharath = sampleId === 'dl_bharath' || fileName?.toLowerCase().includes('bharath');
      actions.setIsMockVector(!isBharath);
      actions.selectFile(fileObj);
    } catch (err) {
      console.error('Failed to load sample document:', err);
      actions.setError(`Unable to load sample: ${err.message}`);
    } finally {
      setLoadingSampleId(null);
    }
  }

  async function handleStartVerification() {
    if (!session.file) return;
    setIsVerifyingWithTimer(true);
    setElapsedMs(0);
    setCompletedSeconds(null);
    const startTime = Date.now();

    const timer = setInterval(() => {
      setElapsedMs(Date.now() - startTime);
    }, 40);

    try {
      await submitOCR(session.file, session.documentType);
      const totalSec = ((Date.now() - startTime) / 1000).toFixed(1);
      setCompletedSeconds(totalSec);
      actions.setVerificationDuration(totalSec);
      clearInterval(timer);
      // Brief pause so the user sees the completed duration, then automatically advance to Stage 2
      setTimeout(() => {
        actions.setWorkflowStage(2);
        setIsVerifyingWithTimer(false);
      }, 700);
    } catch (err) {
      console.error('Inspection process error:', err);
      clearInterval(timer);
      setIsVerifyingWithTimer(false);
    }
  }

  function getCleanSampleDetails(sample) {
    const isBharath = sample.id?.includes('bharath') || sample.label?.includes('Bharath');
    const isDefect = sample.id?.includes('defective') || sample.badge?.includes('DEFECT') || sample.id?.includes('fake');
    const isBlacklist = sample.id?.includes('blacklist') || sample.badge?.includes('BLACKLIST') || sample.id?.includes('revoked');

    let badge = isDefect ? 'FLAGGED / DEFECT' : isBlacklist ? 'WATCHLIST HIT' : isBharath ? 'GENUINE SPECIMEN' : (sample.badge || 'OFFICIAL / ACTIVE');
    let cleanDesc = sample.description || '';

    cleanDesc = cleanDesc
      .replace(/with valid ICAO TD3 MRZ\.?/gi, 'with confirmed authority issuance.')
      .replace(/ICAO TD3 MRZ/gi, 'Official Travel Standard')
      .replace(/Failed check digits & expiry precedes issue date\.?/gi, 'Security feature anomalies & date chronology violations detected.')
      .replace(/Status: REVOKED on national fraud & border watchlist\.?/gi, 'Record flagged as REVOKED on national security watchlist.')
      .replace(/Status: ACTIVE in official registry/gi, 'Status: ACTIVE in official government records');

    return { badge, cleanDesc, isBharath, isDefect, isBlacklist };
  }

  return (
    <div className={styles.stageContainer}>
      {/* ── Section 1: Header ── */}
      <div className={styles.headerBlock}>
        <div className={styles.badgeRow}>
          <span className={styles.stageBadge}>BORDER CONTROL · INTAKE</span>
        </div>
        <h2 className={styles.mainTitle}>Select Document Category</h2>
      </div>

      {/* ── Section 2: Document Category Cards ── */}
      <div className={styles.categoryGrid} role="tablist" aria-label="Document Type Selection">
        {DOC_CATEGORIES.map((cat) => {
          const isSelected = session.documentType === cat.type;
          return (
            <button
              key={cat.type}
              type="button"
              role="tab"
              aria-selected={isSelected}
              className={`${styles.categoryCard} ${isSelected ? styles.categoryCardActive : ''}`}
              onClick={() => handleCategorySelect(cat.type)}
              disabled={isProcessing}
            >
              <div className={styles.catTop}>
                <div className={styles.catIcon}>{cat.icon}</div>
              </div>
              <span className={styles.catLabel}>{cat.label}</span>
              <p className={styles.catDesc}>{cat.desc}</p>
              {isSelected && (
                <div className={styles.selectedIndicator}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  <span>Selected</span>
                </div>
              )}
            </button>
          );
        })}
      </div>

      {/* ── Section 3: ONE-CLICK TEST VECTORS (Prominent Mock Data Section) ── */}
      {!hasFile && !isProcessing && (
        <div className={styles.sampleVectorsSection}>
          <div className={styles.sampleHeader}>
            <div className={styles.sampleTitleRow}>
              <span className={styles.sampleTitle}>Official Reference Profiles</span>
            </div>
          </div>

          <div className={styles.sampleGrid}>
            {currentSamples.map((sample) => {
              const { badge, cleanDesc, isBharath, isDefect, isBlacklist } = getCleanSampleDetails(sample);
              const isLoadingThis = loadingSampleId === sample.id;

              let cardStyle = styles.sampleCard;
              let badgeStyle = styles.sampleBadgeOfficial;

              if (isBharath) {
                cardStyle = `${styles.sampleCard} ${styles.sampleCardBharath}`;
                badgeStyle = styles.sampleBadgeBharath;
              } else if (isDefect) {
                cardStyle = `${styles.sampleCard} ${styles.sampleCardDefect}`;
                badgeStyle = styles.sampleBadgeDefect;
              } else if (isBlacklist) {
                cardStyle = `${styles.sampleCard} ${styles.sampleCardBlacklist}`;
                badgeStyle = styles.sampleBadgeBlacklist;
              }

              return (
                <button
                  key={sample.id}
                  type="button"
                  className={cardStyle}
                  onClick={() => handleLoadSample(sample)}
                  disabled={Boolean(loadingSampleId)}
                >
                  <div className={styles.sampleTop}>
                    <span className={badgeStyle}>
                      {badge}
                    </span>
                  </div>
                  <span className={styles.sampleCardLabel}>
                    {isLoadingThis ? 'Loading Dossier...' : sample.label}
                  </span>
                  <p className={styles.sampleCardDesc}>{cleanDesc}</p>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Section 4: Physical Document Upload DropZone & Preview ── */}
      <div className={styles.uploadSection}>
        <div className={styles.uploadSectionHeader}>
          <h3 className={styles.uploadTitle}>Upload Document</h3>
          <span className={styles.uploadHint}>JPEG, PNG, WebP</span>
        </div>

        {session.error && (
          <div className={styles.errorAlert} role="alert">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>{session.error}</span>
            <button type="button" onClick={() => actions.clearError()} className={styles.dismissBtn}>✕</button>
          </div>
        )}

        {!hasFile && !isProcessing && (
          <div className={styles.dropZoneWrap}>
            <DropZone
              onFileAccepted={handleFileAccepted}
              onError={handleFileError}
              acceptedMimeTypes={profile.acceptedMimeTypes}
              maxFileSizeMB={profile.maxFileSizeMB}
            />
          </div>
        )}

        {hasFile && !isProcessing && (
          <div className={styles.previewCard}>
            <div className={styles.previewThumbBox}>
              {filePreviewUrl ? (
                <img src={filePreviewUrl} alt="Document preview" className={styles.previewImg} />
              ) : (
                <div className={styles.previewPlaceholder}>
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <rect x="3" y="4" width="18" height="16" rx="2" />
                    <line x1="7" y1="8" x2="17" y2="8" />
                  </svg>
                </div>
              )}
            </div>

            <div className={styles.previewDetails}>
              <div className={styles.previewBadgeRow}>
                <span className={styles.loadedBadge}>DOCUMENT READY FOR INSPECTION</span>
                <span className={styles.categoryBadge}>{profile.label.toUpperCase()}</span>
                {session.isMockVector ? (
                  <span className={styles.mockModeBadge}>SAMPLE PROFILE</span>
                ) : (
                  <span className={styles.realDocBadge}>UPLOADED DOCUMENT</span>
                )}
              </div>
              <h3 className={styles.previewFileName}>{session.fileName}</h3>
              <p className={styles.previewMeta}>
                Size: {session.file?.size ? `${(session.file.size / 1024).toFixed(1)} KB` : 'Standard Image'} &bull; Format: {session.file?.type || 'image/jpeg'}
              </p>
              <div className={styles.previewNotice}>
                {session.isMockVector ? (
                  <span>Click <strong>"Start Automated Inspection"</strong> to verify document validity and official records.</span>
                ) : (
                  <span>Click <strong>"Start Automated Inspection"</strong> to verify document authenticity, followed by face photo verification in Stage 3.</span>
                )}
              </div>
            </div>

            <button
              type="button"
              className={styles.removeBtn}
              onClick={handleClearFile}
              title="Remove document and pick another"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
              <span>Change File</span>
            </button>
          </div>
        )}

        {/* Catchy Animated Inspection Timer */}
        {isProcessing && (
          <div className={styles.timerCard}>
            <div className={styles.timerVisualCol}>
              <div className={styles.gaugeContainer}>
                <svg className={styles.gaugeSvg} viewBox="0 0 100 100">
                  <circle
                    className={styles.gaugeBgCircle}
                    cx="50"
                    cy="50"
                    r="42"
                  />
                  <circle
                    className={styles.gaugeBarCircle}
                    cx="50"
                    cy="50"
                    r="42"
                    style={{
                      strokeDashoffset: `${Math.max(0, 264 - (elapsedMs / 2500) * 264)}`,
                    }}
                  />
                </svg>
                <div className={styles.gaugeCenter}>
                  <span className={styles.gaugeSeconds}>
                    {completedSeconds ? `${completedSeconds}s` : `${(elapsedMs / 1000).toFixed(1)}s`}
                  </span>
                  <span className={styles.gaugeLabel}>
                    {completedSeconds ? 'DONE' : 'ELAPSED'}
                  </span>
                </div>
              </div>
            </div>

            <div className={styles.timerDetailsCol}>
              <div className={styles.timerStatusHeader}>
                <span className={styles.timerLiveBadge}>
                  <span className={`${styles.pulsingDot} ${completedSeconds ? styles.dotCompleted : ''}`} />
                  {completedSeconds ? 'VERIFICATION COMPLETED' : 'INSPECTION IN PROGRESS'}
                </span>
                <span className={styles.timerSecondsBadge}>
                  ⏱️ {completedSeconds ? `Completed in ${completedSeconds}s` : `${(elapsedMs / 1000).toFixed(1)} seconds`}
                </span>
              </div>

              <h4 className={styles.timerMainHeading}>
                {completedSeconds
                  ? `Inspection Completed in ${completedSeconds}s! Proceeding to Stage 2...`
                  : 'Automated Document Inspection Running...'}
              </h4>

              <p className={styles.timerSubText}>
                {completedSeconds
                  ? 'All document validity, tampering checks, and records verified. Proceeding to inspection report.'
                  : elapsedMs < 400
                  ? 'Extracting document text and holder identification details...'
                  : elapsedMs < 800
                  ? 'Verifying validity dates and document authenticity...'
                  : elapsedMs < 1200
                  ? 'Scanning for alterations or photo tampering...'
                  : 'Cross-checking official records & finalizing verification report...'}
              </p>

              <div className={styles.timerStepsRow}>
                <div className={`${styles.timerStep} ${elapsedMs >= 50 ? styles.stepActive : ''} ${elapsedMs >= 400 ? styles.stepDone : ''}`}>
                  <span className={styles.stepNum}>{elapsedMs >= 400 ? '✓' : '1'}</span>
                  <span>Extract Details</span>
                </div>
                <div className={`${styles.timerStep} ${elapsedMs >= 400 ? styles.stepActive : ''} ${elapsedMs >= 800 ? styles.stepDone : ''}`}>
                  <span className={styles.stepNum}>{elapsedMs >= 800 ? '✓' : '2'}</span>
                  <span>Verify Dates</span>
                </div>
                <div className={`${styles.timerStep} ${elapsedMs >= 800 ? styles.stepActive : ''} ${elapsedMs >= 1200 ? styles.stepDone : ''}`}>
                  <span className={styles.stepNum}>{elapsedMs >= 1200 ? '✓' : '3'}</span>
                  <span>Tamper Check</span>
                </div>
                <div className={`${styles.timerStep} ${elapsedMs >= 1200 ? styles.stepActive : ''} ${completedSeconds ? styles.stepDone : ''}`}>
                  <span className={styles.stepNum}>{completedSeconds ? '✓' : '4'}</span>
                  <span>Official Records</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Section 5: Primary Next Action Bar ── */}
      {hasFile && !isProcessing && (
        <div className={styles.actionBar}>
          <div className={styles.actionInfo}>
            <span className={styles.readyTag}>Ready to Inspect</span>
            <span className={styles.readyFileName}>{session.fileName}</span>
          </div>

          <button
            type="button"
            className={styles.proceedBtn}
            onClick={handleStartVerification}
            disabled={isSubmitting}
          >
            <span>Start Automated Inspection &amp; Proceed to Stage 2</span>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="5" y1="12" x2="19" y2="12" />
              <polyline points="12 5 19 12 12 19" />
            </svg>
          </button>
        </div>
      )}
    </div>
  );
}
