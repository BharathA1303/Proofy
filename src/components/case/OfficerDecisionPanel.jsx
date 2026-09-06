/**
 * OfficerDecisionPanel.jsx
 *
 * Phase 12 Officer Decision Support & Non-Autonomous Decision Safety.
 * Strictly separates System AI Evaluation from Authoritative Human Officer Action.
 * Anchors the recorded officer decision to the immutable cryptographic audit ledger.
 */
import React, { useState } from 'react';
import styles from './OfficerDecisionPanel.module.css';
import { recordOfficerDecision } from '../../services/auditApi.js';

export default function OfficerDecisionPanel({ targetId, riskAssessment, onDecisionRecorded }) {
  const [officerId, setOfficerId] = useState('OFFICER-BORDER-01');
  const [decision, setDecision] = useState('REFER_TO_SECONDARY');
  const [reason, setReason] = useState('Interim evaluation requires secondary examination of documents.');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [committedBlock, setCommittedBlock] = useState(null);
  const [error, setError] = useState(null);

  const recommendation = riskAssessment?.recommendation || 'REQUIRES_REVIEW';
  const riskLevel = (riskAssessment?.level || riskAssessment?.risk_level || 'MEDIUM').toUpperCase();
  const riskScore = riskAssessment?.composite_score ?? riskAssessment?.score ?? 0.5;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!targetId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await recordOfficerDecision(targetId, {
        officer_id: officerId,
        decision: decision,
        reason: reason,
        notes: notes || undefined,
      });
      setCommittedBlock(res);
      if (onDecisionRecorded) {
        onDecisionRecorded(res);
      }
    } catch (err) {
      setError(err.message || 'Failed to record officer decision to ledger');
    } finally {
      setLoading(false);
    }
  };

  const getRecommendationStyle = (lvl) => {
    if (lvl === 'LOW') return styles.evalLow;
    if (lvl === 'HIGH' || lvl === 'CRITICAL') return styles.evalHigh;
    return styles.evalMedium;
  };

  return (
    <div className={styles.container} id="officer-decision-panel">
      {/* Header */}
      <div className={styles.header}>
        <div>
          <h3 className={styles.title}>Officer Decision Support & Authorization</h3>
          <span className={styles.subtitle}>
            Decision Support Architecture · Human-in-the-Loop Enforcement · Non-Autonomous Outcomes
          </span>
        </div>
      </div>

      {/* Error alert */}
      {error && (
        <div style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c', padding: '0.6rem 0.85rem', borderRadius: '6px', fontSize: '0.8rem' }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Committed Block Confirmation */}
      {committedBlock && (
        <div className={styles.committedAlert} role="status">
          <div style={{ fontWeight: 600 }}>
            &#10003; Officer Decision Anchored to Cryptographic Ledger (Block #{committedBlock.block_index})
          </div>
          <div style={{ fontSize: '0.75rem', fontFamily: 'monospace' }}>
            Digest: {committedBlock.event_hash}
          </div>
          <div style={{ fontSize: '0.75rem' }}>
            Action: <strong>{committedBlock.decision}</strong> by {committedBlock.officer_id} at{' '}
            {new Date(committedBlock.anchored_at).toLocaleString()}
          </div>
        </div>
      )}

      {/* Grid: System Evaluation vs Human Officer Action */}
      <div className={styles.comparisonGrid}>
        {/* Left: System Automated Evaluation */}
        <div className={styles.systemCard}>
          <div className={styles.cardHeading}>
            <span>1. Automated System Evaluation (Advisory)</span>
          </div>

          <div>
            <span className={`${styles.evalRecommendation} ${getRecommendationStyle(riskLevel)}`}>
              {recommendation.replace(/_/g, ' ')}
            </span>
          </div>

          <div className={styles.evalExplanation}>
            <strong>Composite Risk Level:</strong> {riskLevel} ({Math.round(riskScore * 100)}%)<br />
            {riskAssessment?.explanation ||
              'Automated composite evaluation based on OCR, forensic signals, biometrics, registry match, and cross-document consistency.'}
          </div>

          <div className={styles.disclaimerNotice}>
            <strong>Mandatory Operational Rule:</strong> The automated system evaluation is strictly advisory. The software does not possess authority to grant admission or deny entry.
          </div>
        </div>

        {/* Right: Authoritative Officer Action */}
        <form className={styles.officerForm} onSubmit={handleSubmit}>
          <div className={styles.cardHeading}>
            <span>2. Authoritative Officer Action</span>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label} htmlFor="officer-id-input">
              Authorized Officer ID / Badge Number
            </label>
            <input
              id="officer-id-input"
              type="text"
              className={styles.input}
              value={officerId}
              onChange={(e) => setOfficerId(e.target.value)}
              required
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label} htmlFor="officer-action-select">
              Operational Determination
            </label>
            <select
              id="officer-action-select"
              className={styles.select}
              value={decision}
              onChange={(e) => setDecision(e.target.value)}
            >
              <option value="CLEAR_ADMIT">ADMIT / CLEAR (Pass Entry)</option>
              <option value="REFER_TO_SECONDARY">REFER TO SECONDARY INSPECTION (Requires In-Depth Review)</option>
              <option value="REQUEST_ADDITIONAL_DOCUMENTS">REQUEST ADDITIONAL DOCUMENTS (Missing Credentials)</option>
              <option value="REFUSE_ENTRY">REFUSE ENTRY (Inadmissible / Confirmed Fraud)</option>
            </select>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label} htmlFor="officer-reason-input">
              Operational Justification / Primary Reason
            </label>
            <input
              id="officer-reason-input"
              type="text"
              className={styles.input}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              required
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label} htmlFor="officer-notes-input">
              Operational Notes (Optional)
            </label>
            <textarea
              id="officer-notes-input"
              className={styles.textarea}
              placeholder="Record any physical interview notes or manual override rationale..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>

          <button
            type="submit"
            className={styles.submitBtn}
            disabled={loading || !targetId}
            id="btn-commit-officer-decision"
          >
            {loading ? 'Anchoring to Ledger...' : 'Commit Decision to Cryptographic Ledger'}
          </button>
        </form>
      </div>
    </div>
  );
}
