/**
 * CrossDocumentPanel.jsx
 *
 * Displays cross-document consistency comparisons and relationship evidence
 * between pairs of documents in the verification case.
 */
import React from 'react';
import styles from './CaseWorkspace.module.css';

export default function CrossDocumentPanel({ relationships = [], onReevaluate, loading }) {
  if (!relationships || relationships.length === 0) {
    return (
      <section className={styles.consistencySection} aria-labelledby="cross-doc-heading">
        <div className={styles.sectionHeader}>
          <h2 id="cross-doc-heading" className={styles.sectionTitle}>
            Cross-Document Consistency
          </h2>
        </div>
        <p className={styles.caseMeta}>
          Cross-document consistency analysis requires at least two operational identity documents
          belonging to this case. Upload a second document to evaluate field relationships.
        </p>
      </section>
    );
  }

  return (
    <section className={styles.consistencySection} aria-labelledby="cross-doc-heading">
      <div className={styles.sectionHeader}>
        <div>
          <h2 id="cross-doc-heading" className={styles.sectionTitle}>
            Cross-Document Consistency ({relationships.length} Relationships)
          </h2>
          <span style={{ fontSize: '0.8125rem', color: '#64748b' }}>
            Deterministic field correlation and provenance verification
          </span>
        </div>
        <button
          type="button"
          className={styles.btnSecondary}
          onClick={onReevaluate}
          disabled={loading}
          id="btn-reevaluate-relationships"
        >
          {loading ? 'Re-evaluating...' : 'Re-evaluate Relationships'}
        </button>
      </div>

      <table className={styles.relationshipTable} aria-label="Cross-document relationships">
        <thead>
          <tr>
            <th scope="col">Relationship Type</th>
            <th scope="col">Field Comparison</th>
            <th scope="col">Values Observed</th>
            <th scope="col">Consistency Status</th>
            <th scope="col">Evidence Explanation</th>
          </tr>
        </thead>
        <tbody>
          {relationships.map((rel, idx) => {
            const isMatch = rel.status === 'MATCHED';
            const isMismatch = rel.status === 'MISMATCH';
            const isPartial = rel.status === 'PARTIAL_MATCH';

            const statusClass = isMatch
              ? styles.statusMatched
              : isMismatch
              ? styles.statusMismatch
              : isPartial
              ? styles.statusPartial
              : styles.statusMissing;

            const isHighSev = rel.severity === 'HIGH' || rel.severity === 'CRITICAL';
            const isLowSev = rel.severity === 'LOW' || rel.severity === 'MEDIUM';

            return (
              <tr key={rel.evidence_id || idx} id={`rel-row-${idx}`}>
                <td>
                  <span style={{ fontWeight: 600, color: '#334155' }}>
                    {rel.relationship_type ? rel.relationship_type.replace(/_/g, ' ') : 'CONSISTENCY'}
                  </span>
                </td>

                <td>
                  <span className={styles.fieldLabel}>
                    {rel.source_document?.field || 'source'} ↔ {rel.target_document?.field || 'target'}
                  </span>
                </td>

                <td>
                  <div className={styles.comparisonValues}>
                    <div className={styles.valRow}>
                      <span className={styles.valDocType}>{rel.source_document?.document_type}:</span>
                      <span className={styles.valData}>
                        {rel.source_document?.value != null ? String(rel.source_document.value) : '—'}
                      </span>
                    </div>
                    <div className={styles.valRow}>
                      <span className={styles.valDocType}>{rel.target_document?.document_type}:</span>
                      <span className={styles.valData}>
                        {rel.target_document?.value != null ? String(rel.target_document.value) : '—'}
                      </span>
                    </div>
                  </div>
                </td>

                <td>
                  <div style={{ display: 'flex', alignItems: 'center' }}>
                    <span className={`${styles.statusBadge} ${statusClass}`}>
                      {isMatch && '✓ '}
                      {isMismatch && '⚠ '}
                      {rel.status}
                    </span>
                    {isHighSev && (
                      <span className={`${styles.severityTag} ${styles.severityHigh}`}>
                        {rel.severity}
                      </span>
                    )}
                    {isLowSev && (
                      <span className={`${styles.severityTag} ${styles.severityLow}`}>
                        {rel.severity}
                      </span>
                    )}
                  </div>
                </td>

                <td>
                  <div className={styles.explanationText}>
                    {rel.explanation}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
