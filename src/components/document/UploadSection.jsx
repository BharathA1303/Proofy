/**
 * UploadSection.jsx
 *
 * Left column of the 3-column workspace matching the exact reference image:
 * - Step 1: Upload Document header with 'Need help?' link
 * - Cloud icon drag & drop area with 'Choose File' button
 * - Document type selector buttons (Passport, Visa, Driving License, National ID, Border Permit)
 * - 'Tips for best results' callout box
 */
import { useRef, useState } from 'react';
import { useVerification } from '../../state/verification/useVerification.js';
import { DOCUMENT_TYPES, DOCUMENT_PROFILES } from '../../config/documentProfiles.js';
import { useOCRSubmit } from '../../services/useOCRSubmit.js';
import styles from './UploadSection.module.css';

const DOC_TABS = [
  { key: DOCUMENT_TYPES.PASSPORT,        label: 'Passport',        icon: 'passport' },
  { key: DOCUMENT_TYPES.VISA,            label: 'Visa',            icon: 'visa' },
  { key: DOCUMENT_TYPES.DRIVING_LICENSE, label: 'Driving License', icon: 'license' },
  { key: DOCUMENT_TYPES.NATIONAL_ID,     label: 'National ID',     icon: 'id' },
  { key: DOCUMENT_TYPES.BORDER_PERMIT,   label: 'Border Permit',   icon: 'permit' },
];

export default function UploadSection() {
  const { session, actions } = useVerification();
  const { submitOCR, isSubmitting } = useOCRSubmit();
  const fileInputRef = useRef(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const currentType = session.documentType;
  const currentFile = session.file;

  function handleFileChange(e) {
    const file = e.target.files?.[0];
    if (file) {
      actions.clearError();
      actions.selectFile(file);
    }
  }

  function handleDrop(e) {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      actions.clearError();
      actions.selectFile(file);
    }
  }

  function handleDragOver(e) {
    e.preventDefault();
    setIsDragOver(true);
  }

  function handleDragLeave() {
    setIsDragOver(false);
  }

  async function handleLoadSample(typeKey) {
    actions.clearError();
    try {
      let endpoint = `/api/v1/verification/sample/${typeKey}`;
      const res = await fetch(endpoint);
      if (res.ok) {
        const blob = await res.blob();
        const sampleFile = new File([blob], `Sample_${typeKey}.jpg`, { type: 'image/jpeg' });
        actions.selectFile(sampleFile);
        return;
      }
    } catch {
      // Fallback
    }
    const profile = DOCUMENT_PROFILES[typeKey];
    actions.selectSample(`Sample_${profile?.label || 'Doc'}.jpg`, `sample_${typeKey}`);
  }

  return (
    <div className={styles.cardContainer}>
      {/* Header */}
      <div className={styles.cardHeader}>
        <div className={styles.headerLeft}>
          <div className={styles.stepBadge}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </div>
          <div className={styles.headerTitles}>
            <h2 className={styles.headerMainTitle}>Step 1: Upload Document</h2>
            <p className={styles.headerSubtitle}>Upload a clear image or scan of the travel document</p>
          </div>
        </div>
        <a href="#help" className={styles.helpLink} onClick={(e) => e.preventDefault()}>Need help?</a>
      </div>

      {/* Drag & Drop Zone */}
      <div
        className={`${styles.dropZone} ${isDragOver ? styles.dropZoneActive : ''}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,application/pdf"
          className={styles.hiddenInput}
          onChange={handleFileChange}
        />

        <div className={styles.cloudIconCircle}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z" />
            <polyline points="12 11 12 16" />
            <polyline points="9 13 12 10 15 13" />
          </svg>
        </div>

        <p className={styles.dropMainText}>Drag & drop document here</p>
        <p className={styles.dropSubText}>or click to browse</p>

        <button
          type="button"
          className={styles.chooseFileBtn}
          onClick={(e) => {
            e.stopPropagation();
            fileInputRef.current?.click();
          }}
        >
          Choose File
        </button>

        <span className={styles.formatText}>Supports JPEG, PNG, WEBP, PDF | Max size: 10 MB</span>
      </div>

      {/* Selected File Feedback & Pipeline Action */}
      {currentFile && (
        <div className={styles.fileSelectedBox}>
          <div className={styles.fileInfoGroup}>
            <span className={styles.fileLabel}>Selected:</span>
            <span className={styles.fileNameText}>{session.fileName}</span>
          </div>
          <button
            type="button"
            className={styles.runPipelineBtn}
            onClick={() => submitOCR(session.file, session.documentType)}
            disabled={isSubmitting}
          >
            {isSubmitting ? 'Running Inspection...' : '⚡ Run Verification Pipeline'}
          </button>
        </div>
      )}

      {/* Document Type Selector Tabs */}
      <div className={styles.docTypeTabsRow} role="tablist" aria-label="Select Document Type">
        {DOC_TABS.map((tab) => {
          const isSelected = currentType === tab.key;
          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={isSelected}
              className={`${styles.tabBtn} ${isSelected ? styles.tabBtnActive : ''}`}
              onClick={() => {
                actions.setDocumentType(tab.key);
                handleLoadSample(tab.key);
              }}
            >
              <span className={styles.tabIcon}>
                {tab.icon === 'passport' && '📄'}
                {tab.icon === 'visa' && '📄'}
                {tab.icon === 'license' && '💳'}
                {tab.icon === 'id' && '🪪'}
                {tab.icon === 'permit' && '🛂'}
              </span>
              <span className={styles.tabLabel}>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Tips Callout Container */}
      <div className={styles.tipsContainer}>
        <div className={styles.tipsTitleRow}>
          <span className={styles.tipsBulbIcon}>💡</span>
          <span className={styles.tipsTitle}>Tips for best results:</span>
        </div>
        <ul className={styles.tipsList}>
          <li>• Use a clear, well-lit image</li>
          <li>• Ensure all corners are visible</li>
          <li>• Avoid glare and blur</li>
        </ul>
      </div>
    </div>
  );
}
