/**
 * DropZone.jsx
 *
 * Drag-and-drop file upload area.
 *
 * - Validates file type against profile.acceptedMimeTypes
 * - Validates file size against profile.maxFileSizeMB
 * - Calls onFileAccepted(file) on valid drop or Choose File selection
 * - Calls onError(message) on invalid file
 * - Does NOT trigger any backend call
 * - Does NOT auto-load anything on mount
 */
import { useState, useRef, useId } from 'react';
import styles from './DropZone.module.css';

/**
 * @param {{
 *   onFileAccepted: (file: File) => void,
 *   onError: (message: string) => void,
 *   acceptedMimeTypes: string[],
 *   maxFileSizeMB: number,
 *   disabled?: boolean
 * }} props
 */
export default function DropZone({ onFileAccepted, onError, acceptedMimeTypes, maxFileSizeMB, disabled = false }) {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef(null);
  const inputId = useId();

  function validateAndAccept(file) {
    if (!file) return;

    if (!acceptedMimeTypes.includes(file.type)) {
      onError('Unsupported document format. Please upload a JPEG, PNG, WebP, or PDF file.');
      return;
    }

    const maxBytes = maxFileSizeMB * 1024 * 1024;
    if (file.size > maxBytes) {
      onError(`File is too large. Maximum allowed size is ${maxFileSizeMB} MB.`);
      return;
    }

    onFileAccepted(file);
  }

  /* ---------- Drag handlers ---------- */

  function handleDragOver(e) {
    e.preventDefault();
    if (!disabled) setIsDragging(true);
  }

  function handleDragLeave(e) {
    // Only clear if leaving the zone entirely (not a child element)
    if (!e.currentTarget.contains(e.relatedTarget)) {
      setIsDragging(false);
    }
  }

  function handleDrop(e) {
    e.preventDefault();
    setIsDragging(false);
    if (disabled) return;

    const file = e.dataTransfer.files?.[0];
    validateAndAccept(file);
  }

  /* ---------- File input handler ---------- */

  function handleFileInputChange(e) {
    const file = e.target.files?.[0];
    validateAndAccept(file);
    // Reset input so the same file can be re-selected after clearing
    e.target.value = '';
  }

  /* ---------- Click to open file dialog ---------- */

  function handleZoneClick() {
    if (!disabled) inputRef.current?.click();
  }

  function handleKeyDown(e) {
    if (!disabled && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      inputRef.current?.click();
    }
  }

  const acceptAttr = acceptedMimeTypes.join(',');

  return (
    <div
      className={`${styles.zone} ${isDragging ? styles.dragging : ''} ${disabled ? styles.disabled : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={handleZoneClick}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label="Drop document here or click to choose a file"
      aria-disabled={disabled}
    >
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={acceptAttr}
        onChange={handleFileInputChange}
        className={styles.hiddenInput}
        aria-hidden="true"
        tabIndex={-1}
        disabled={disabled}
      />

      <div className={styles.content}>
        <div className={styles.iconCircle}>
          <svg
            className={styles.uploadIcon}
            xmlns="http://www.w3.org/2000/svg"
            width="28"
            height="28"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </div>

        <div className={styles.textGroup}>
          <p className={styles.primary}>
            {isDragging ? 'Drop document to upload' : 'Drag & drop document here'}
          </p>
          <p className={styles.secondary}>Supports high-resolution camera captures and scans</p>
        </div>

        <button className={styles.browseBtn} type="button" tabIndex={-1}>
          Choose File
        </button>

        <div className={styles.metaRow}>
          <div className={styles.formatList}>
            {acceptedMimeTypes.map((m) => (
              <span key={m} className={styles.formatTag}>
                {m.split('/')[1].toUpperCase()}
              </span>
            ))}
          </div>
          <span className={styles.sizeInfo}>Max {maxFileSizeMB} MB</span>
        </div>
      </div>
    </div>
  );
}


