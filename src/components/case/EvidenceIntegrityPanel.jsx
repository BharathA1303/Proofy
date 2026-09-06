/**
 * EvidenceIntegrityPanel.jsx
 *
 * Phase 12 Blockchain Audit & Cryptographic Evidence Integrity.
 * Provides on-chain audit status, SHA-256 evidence integrity verification,
 * and an expandable cryptographic chain-of-custody inspection drawer.
 */
import React, { useState, useEffect, useCallback } from 'react';
import styles from './EvidenceIntegrityPanel.module.css';
import { getAuditChain, verifyIntegrity } from '../../services/auditApi.js';

export default function EvidenceIntegrityPanel({ targetId, initialAudit }) {
  const [chain, setChain] = useState(null);
  const [verificationResult, setVerificationResult] = useState(null);
  const [loadingVerify, setLoadingVerify] = useState(false);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [error, setError] = useState(null);

  // Fetch chain when drawer opens or when targetId changes
  const fetchChain = useCallback(async () => {
    if (!targetId) return;
    try {
      const data = await getAuditChain(targetId);
      setChain(data);
    } catch (err) {
      setError(err.message || 'Failed to load audit chain');
    }
  }, [targetId]);

  useEffect(() => {
    let isSubscribed = true;
    if (!targetId) return;

    getAuditChain(targetId)
      .then((data) => {
        if (isSubscribed) setChain(data);
      })
      .catch((err) => {
        if (isSubscribed) setError(err.message || 'Failed to load audit chain');
      });

    return () => {
      isSubscribed = false;
    };
  }, [targetId]);

  // Handle live integrity verification
  const handleVerify = async () => {
    if (!targetId) return;
    setLoadingVerify(true);
    setError(null);
    try {
      const res = await verifyIntegrity(targetId);
      setVerificationResult(res);
      // Refresh chain data after verification
      await fetchChain();
    } catch (err) {
      setError(err.message || 'Integrity verification failed');
    } finally {
      setLoadingVerify(false);
    }
  };

  const blockCount = chain?.total_blocks ?? initialAudit?.events_count ?? 0;
  const chainValid = chain?.chain_valid ?? initialAudit?.chain_valid ?? true;
  const ledgerType = chain?.ledger_type ?? initialAudit?.ledger_type ?? 'development_sandbox';
  const latestHash = chain?.blocks?.length > 0 ? chain.blocks[chain.blocks.length - 1].block_hash : null;

  return (
    <div className={styles.container} id="evidence-integrity-panel">
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <div className={styles.iconBadge} aria-hidden="true">&#9930;</div>
          <div>
            <h3 className={styles.title}>Cryptographic Evidence Integrity & Audit Trail</h3>
            <span className={styles.subtitle}>
              Immutable SHA-256 Ledger · Zero PII On-Chain · Canonical Hashing
            </span>
          </div>
        </div>

        <div>
          {chainValid ? (
            <span className={`${styles.statusPill} ${styles.statusValid}`}>
              &#10003; Chain Valid
            </span>
          ) : (
            <span className={`${styles.statusPill} ${styles.statusTampered}`}>
              &#9888; Integrity Failure
            </span>
          )}
        </div>
      </div>

      {/* Error alert if any */}
      {error && (
        <div className={`${styles.resultAlert} ${styles.resultDanger}`}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Meta Grid */}
      <div className={styles.metaGrid}>
        <div className={styles.metaItem}>
          <span className={styles.metaLabel}>Ledger Subsystem</span>
          <span className={styles.metaValue}>
            {ledgerType === 'development_sandbox'
              ? 'Local Development Sandbox'
              : 'Permissioned Ledger'}
          </span>
        </div>
        <div className={styles.metaItem}>
          <span className={styles.metaLabel}>Target Identifier</span>
          <span className={`${styles.metaValue} ${styles.mono}`}>{targetId || '—'}</span>
        </div>
        <div className={styles.metaItem}>
          <span className={styles.metaLabel}>Anchored Events</span>
          <span className={styles.metaValue}>{blockCount} block(s) recorded</span>
        </div>
        <div className={styles.metaItem}>
          <span className={styles.metaLabel}>Head Block Hash</span>
          <span className={`${styles.metaValue} ${styles.mono}`} title={latestHash || 'Genesis'}>
            {latestHash ? `${latestHash.slice(0, 16)}...` : 'Genesis'}
          </span>
        </div>
      </div>

      {/* Action Bar */}
      <div className={styles.actionBar}>
        <button
          type="button"
          className={styles.verifyBtn}
          onClick={handleVerify}
          disabled={loadingVerify || !targetId}
          id="btn-verify-blockchain-integrity"
        >
          {loadingVerify ? 'Recalculating SHA-256 Hashes...' : 'Verify Cryptographic Integrity'}
        </button>

        <button
          type="button"
          className={styles.toggleBtn}
          onClick={() => setIsDrawerOpen(!isDrawerOpen)}
          id="btn-toggle-audit-chain"
        >
          {isDrawerOpen ? 'Hide Audit Blocks ▲' : `Inspect Audit Trail (${blockCount}) ▼`}
        </button>
      </div>

      {/* Live Verification Result Alert */}
      {verificationResult && (
        <div
          className={`${styles.resultAlert} ${
            verificationResult.integrity_status === 'VALID' ? styles.resultSuccess : styles.resultDanger
          }`}
          role="status"
        >
          {verificationResult.integrity_status === 'VALID' ? (
            <div>
              <strong>Integrity Confirmed:</strong> {verificationResult.message} (
              {verificationResult.events_verified} events verified, recalculated hash matches anchored block).
            </div>
          ) : (
            <div>
              <strong>Cryptographic Integrity Failure:</strong> {verificationResult.message}.
              Evidence package has been modified or does not match anchored SHA-256 digest!
            </div>
          )}
        </div>
      )}

      {/* Expandable Chain Drawer */}
      {isDrawerOpen && (
        <div className={styles.chainDrawer} id="audit-chain-drawer">
          <h4 className={styles.chainTitle}>Anchored Blocks (Hash-Linked Sequence)</h4>
          {chain?.blocks && chain.blocks.length > 0 ? (
            <div className={styles.tableWrapper}>
              <table className={styles.chainTable}>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Event Type</th>
                    <th>Timestamp (UTC)</th>
                    <th>Event Digest (SHA-256)</th>
                    <th>Previous Block Hash</th>
                    <th>Signer / Mode</th>
                  </tr>
                </thead>
                <tbody>
                  {chain.blocks.map((block) => (
                    <tr key={block.block_index}>
                      <td style={{ fontWeight: 600 }}>{block.block_index}</td>
                      <td>
                        <span className={styles.eventBadge}>{block.event_type}</span>
                      </td>
                      <td style={{ whiteSpace: 'nowrap', color: '#64748b' }}>
                        {new Date(block.timestamp).toLocaleString()}
                      </td>
                      <td className={styles.mono} title={block.event_hash}>
                        {block.event_hash ? `${block.event_hash.slice(0, 14)}...` : '—'}
                      </td>
                      <td className={styles.mono} title={block.previous_hash}>
                        {block.previous_hash ? `${block.previous_hash.slice(0, 14)}...` : 'GENESIS'}
                      </td>
                      <td style={{ color: '#475569' }}>{block.signer}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ fontSize: '0.8125rem', color: '#64748b', padding: '0.5rem 0' }}>
              No anchored blocks found for this identifier.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
