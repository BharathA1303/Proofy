/**
 * AddDocumentModal.jsx
 *
 * Modal dialog to attach an additional identity document to a case.
 * Enforces available profiles (Passport, Visa) while displaying
 * future planned types (Driving License, National ID, Border Permit)
 * as 'Coming Soon'.
 */
import React, { useState, useRef } from 'react';
import styles from './CaseWorkspace.module.css';

const DOCUMENT_TYPES = [
  { type: 'passport', label: 'Passport', available: true, standard: 'ICAO Doc 9303 TD3' },
  { type: 'visa', label: 'Visa', available: true, standard: 'MRV-A / MRV-B' },
  { type: 'driving_license', label: 'Driving License', available: true, standard: 'MoRTH / ISO 18013' },
  { type: 'aadhaar', label: 'Aadhaar Card', available: true, standard: 'UIDAI Reference / 12-Digit' },
  { type: 'voter_id', label: 'Voter ID / EPIC', available: true, standard: 'ECI Electoral Credential' },
  { type: 'pan_card', label: 'PAN Card', available: true, standard: 'ITD Taxpayer Identification' },
  { type: 'border_permit', label: 'Border Permit', available: true, standard: 'Regional Entry Reference' },
];

export default function AddDocumentModal({ isOpen, onClose, onAddDocument, loading }) {
  const [selectedType, setSelectedType] = useState('passport');
  const [replace, setReplace] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const fileInputRef = useRef(null);

  if (!isOpen) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!selectedFile) return;
    onAddDocument({
      documentType: selectedType,
      file: selectedFile,
      replace,
    });
  };

  return (
    <div className={styles.modalOverlay} role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div className={styles.modalContent}>
        <div className={styles.modalHeader}>
          <h2 id="modal-title" className={styles.modalTitle}>
            Add Document to Case
          </h2>
          <button
            type="button"
            className={styles.btnSecondary}
            onClick={onClose}
            style={{ padding: '0.2rem 0.5rem', border: 'none' }}
            aria-label="Close dialog"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '0.5rem' }}>
              Select Document Category
            </label>
            <div className={styles.docTypeSelect}>
              {DOCUMENT_TYPES.map((item) => (
                <div
                  key={item.type}
                  className={`${styles.typeOption} ${
                    selectedType === item.type ? styles.typeOptionSelected : ''
                  } ${!item.available ? styles.typeOptionDisabled : ''}`}
                  onClick={() => item.available && setSelectedType(item.type)}
                >
                  <div>
                    <span style={{ fontWeight: 600, color: '#0f172a' }}>{item.label}</span>
                    <span style={{ fontSize: '0.75rem', color: '#64748b', marginLeft: '0.5rem' }}>
                      ({item.standard})
                    </span>
                  </div>
                  <div>
                    {item.available ? (
                      <span style={{ fontSize: '0.75rem', color: '#059669', fontWeight: 600 }}>Available</span>
                    ) : (
                      <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Coming Soon</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div style={{ marginBottom: '1.25rem' }}>
            <label style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '0.5rem' }}>
              Document Image File
            </label>
            <input
              type="file"
              ref={fileInputRef}
              accept="image/jpeg,image/png,image/webp"
              onChange={(e) => setSelectedFile(e.target.files[0] || null)}
              required
              id="input-case-document-file"
              style={{ fontSize: '0.875rem' }}
            />
          </div>

          <div style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <input
              type="checkbox"
              id="chk-replace-document"
              checked={replace}
              onChange={(e) => setReplace(e.target.checked)}
            />
            <label htmlFor="chk-replace-document" style={{ fontSize: '0.8125rem', color: '#475569' }}>
              Replace/supersede existing document of this type if already present
            </label>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
            <button
              type="button"
              className={styles.btnSecondary}
              onClick={onClose}
              disabled={loading}
            >
              Cancel
            </button>
            <button
              type="submit"
              className={styles.btnPrimary}
              disabled={!selectedFile || loading}
              id="btn-submit-add-document"
            >
              {loading ? 'Processing Document...' : 'Attach & Process'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
