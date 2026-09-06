/**
 * CaseDocuments.jsx
 *
 * Renders the documents belonging to a verification case with module
 * completion indicators, document switching, and removal controls.
 */
import React from 'react';
import styles from './CaseWorkspace.module.css';

export default function CaseDocuments({
  documents = [],
  activeDocumentId,
  onSelectDocument,
  onRemoveDocument,
  onOpenAddModal,
}) {
  return (
    <section className={styles.documentsSection} aria-labelledby="case-documents-heading">
      <div className={styles.sectionHeader}>
        <h2 id="case-documents-heading" className={styles.sectionTitle}>
          Case Documents ({documents.length})
        </h2>
        <button
          type="button"
          className={styles.btnPrimary}
          onClick={onOpenAddModal}
          id="btn-add-document"
        >
          + Add Document
        </button>
      </div>

      {documents.length === 0 ? (
        <p className={styles.caseMeta}>No documents attached to this case yet. Click &quot;+ Add Document&quot; to begin.</p>
      ) : (
        <div className={styles.documentCardsGrid}>
          {documents.map((doc) => {
            const isActive = doc.document_id === activeDocumentId;
            const statuses = doc.module_statuses || {};

            return (
              <div
                key={doc.document_id}
                className={`${styles.docCard} ${isActive ? styles.docCardActive : ''}`}
                onClick={() => onSelectDocument(doc.document_id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === 'Enter' && onSelectDocument(doc.document_id)}
                id={`doc-card-${doc.document_id}`}
              >
                <div className={styles.docCardHeader}>
                  <div>
                    <span className={styles.docType}>{doc.document_type}</span>
                    <div style={{ marginTop: '0.2rem' }}>
                      <span className={styles.docId}>{doc.document_id}</span>
                      {doc.document_revision > 1 && (
                        <span style={{ marginLeft: '0.4rem', fontSize: '0.75rem', color: '#64748b' }}>
                          (Rev {doc.document_revision})
                        </span>
                      )}
                    </div>
                  </div>
                  <span className={styles.caseStatus}>
                    {doc.status || 'Completed'}
                  </span>
                </div>

                {/* Module status tags */}
                <div className={styles.moduleBadges}>
                  {['ocr', 'validation', 'forensics', 'biometrics', 'registry'].map((mod, idx) => {
                    const st = statuses[mod];
                    const isDone = st === 'completed' || st === 'MATCHED' || st === 'CLEAR';
                    const isFail = st === 'failed' || st === 'CRITICAL_CONCERN' || st === 'REVOKED';

                    return (
                      <span
                        key={mod}
                        className={`${styles.moduleTag} ${isDone ? styles.moduleTagDone : isFail ? styles.moduleTagFail : ''}`}
                        title={`${mod}: ${st || 'pending'}`}
                      >
                        M{idx + 1} {isDone ? '✓' : isFail ? '✗' : '·'}
                      </span>
                    );
                  })}
                </div>

                <div className={styles.docCardFooter}>
                  <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                    {doc.filename || 'Uploaded file'}
                  </span>
                  <button
                    type="button"
                    className={styles.btnRemove}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (window.confirm(`Remove ${doc.document_type} (${doc.document_id}) from case?`)) {
                        onRemoveDocument(doc.document_id);
                      }
                    }}
                    id={`btn-remove-${doc.document_id}`}
                    aria-label={`Remove document ${doc.document_id}`}
                  >
                    Remove
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
