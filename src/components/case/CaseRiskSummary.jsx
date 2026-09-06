/**
 * CaseRiskSummary.jsx
 *
 * Displays case-level aggregate risk assessment, officer recommendation,
 * conflict detection alerts, and non-autonomous decision support guidance.
 */
import React from 'react';
import styles from './CaseWorkspace.module.css';

export default function CaseRiskSummary({ riskAssessment, onRefreshRisk, loading }) {
  if (!riskAssessment) {
    return (
      <section className={styles.riskSummaryCard} aria-labelledby="case-risk-heading">
        <div className={styles.sectionHeader}>
          <h2 id="case-risk-heading" className={styles.sectionTitle}>
            Case-Level Composite Risk
          </h2>
          <button
            type="button"
            className={styles.btnPrimary}
            onClick={onRefreshRisk}
            disabled={loading}
            id="btn-compute-case-risk"
          >
            {loading ? 'Evaluating...' : 'Compute Case Risk'}
          </button>
        </div>
        <p className={styles.caseMeta}>
          Case risk evaluation pending. Click above to compute composite risk across all documents.
        </p>
      </section>
    );
  }

  const score = riskAssessment.risk_score || 0;
  const level = (riskAssessment.risk_level || 'LOW').toUpperCase();
  const recommendation =
    riskAssessment.recommendation ||
    riskAssessment.officer_recommendation ||
    'STANDARD OFFICER REVIEW';
  const conflictDetected = Boolean(riskAssessment.conflict_detected);
  const completeness = Math.round((riskAssessment.verification_completeness ?? 1) * 100);

  const riskClass =
    level === 'CRITICAL'
      ? styles.riskCritical
      : level === 'HIGH'
      ? styles.riskHigh
      : level === 'MEDIUM'
      ? styles.riskMedium
      : styles.riskLow;

  return (
    <section className={styles.riskSummaryCard} aria-labelledby="case-risk-heading">
      <div className={styles.sectionHeader}>
        <div>
          <h2 id="case-risk-heading" className={styles.sectionTitle}>
            Case-Level Risk & Officer Decision Support
          </h2>
          <span style={{ fontSize: '0.8125rem', color: '#64748b' }}>
            Aggregated cross-document and multi-credential risk assessment
          </span>
        </div>
        <button
          type="button"
          className={styles.btnSecondary}
          onClick={onRefreshRisk}
          disabled={loading}
          id="btn-refresh-case-risk"
        >
          {loading ? 'Refreshing...' : 'Refresh Case Risk'}
        </button>
      </div>

      <div className={styles.riskGrid}>
        {/* Score dial */}
        <div className={`${styles.scoreBadge} ${riskClass}`}>
          <span className={styles.scoreValue}>{score}</span>
          <span className={styles.scoreLabel}>{level}</span>
        </div>

        {/* Officer Recommendation & Details */}
        <div>
          <div className={styles.recommendationGroup}>
            <span className={styles.recLabel}>Officer Recommendation</span>
            <span className={styles.recValue} id="case-recommendation-value">
              {recommendation}
            </span>
          </div>

          {conflictDetected && (
            <div className={styles.conflictAlert} role="alert" id="case-conflict-alert">
              <span>⚠</span>
              <span>
                <strong>Conflicting Evidence Detected:</strong> Cross-document or cross-module findings
                contain contradictory indicators requiring priority officer inspection.
              </span>
            </div>
          )}

          <div style={{ marginTop: '0.75rem', display: 'flex', gap: '1.5rem', fontSize: '0.8125rem', color: '#64748b' }}>
            <div>
              <strong>Completeness:</strong> {completeness}%
            </div>
            <div>
              <strong>Documents Considered:</strong>{' '}
              {(riskAssessment.documents_considered || []).join(', ') || 'None'}
            </div>
            <div>
              <strong>Config Version:</strong> {riskAssessment.risk_config_version || '0.6.0'}
            </div>
          </div>
        </div>
      </div>

      {/* Reasons breakdown */}
      {riskAssessment.reasons && riskAssessment.reasons.length > 0 && (
        <div style={{ marginTop: '1.5rem', borderTop: '1px solid #f1f5f9', paddingTop: '1rem' }}>
          <h3 style={{ fontSize: '0.875rem', fontWeight: 600, color: '#334155', marginBottom: '0.5rem' }}>
            Primary Adverse Findings ({riskAssessment.reasons.length})
          </h3>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            {riskAssessment.reasons.map((r, i) => (
              <li
                key={r.reason_id || i}
                style={{
                  fontSize: '0.8125rem',
                  display: 'flex',
                  justifyContent: 'space-between',
                  padding: '0.4rem 0.6rem',
                  background: '#f8fafc',
                  borderRadius: '4px',
                  border: '1px solid #e2e8f0',
                }}
              >
                <span>
                  <strong>[{r.module}]</strong> {r.explanation}
                </span>
                <span style={{ fontWeight: 600, color: '#dc2626' }}>
                  +{r.contribution?.toFixed(1) || '0.0'} pts
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Statutory guardrail footer */}
      <div
        style={{
          marginTop: '1.25rem',
          padding: '0.75rem 1rem',
          background: '#f8fafc',
          borderRadius: '6px',
          border: '1px solid #e2e8f0',
          fontSize: '0.75rem',
          color: '#64748b',
          lineHeight: '1.4',
        }}
      >
        <strong>Operational Notice:</strong> This score is a deterministic risk signal for authorized
        border screening personnel. The screening terminal never takes autonomous enforcement actions;
        all final clearance or secondary referral decisions are made by an authorized officer.
      </div>
    </section>
  );
}
