/**
 * RegistryStatus.jsx
 *
 * Module 5: Registry Verification Evidence Panel.
 *
 * Displays structured registry verification evidence from the Module 5
 * RegistryVerificationResponse.
 *
 * Architectural guarantees:
 *   - NEVER displays "Government Verified" or "Government Registry"
 *     when source_type='development_mock'.
 *   - NEVER displays CLEARED / DENIED / SAFE / DANGEROUS.
 *   - Only displays structured evidence from registryDetail state.
 *   - Registry status is always labeled clearly.
 *   - provider_metadata.source_type is always visible.
 *
 * Consumed by: VerificationChecks.jsx (as an evidence expansion panel)
 */
import { useState } from 'react';
import { useVerification } from '../../state/verification/useVerification.js';
import styles from './RegistryStatus.module.css';

// ── Status display metadata ─────────────────────────────────────────────────

const STATUS_CONFIG = {
  MATCHED: {
    label: 'MATCHED',
    className: 'statusMatched',
    icon: '✓',
    description: 'All critical identity fields verified against registry.',
  },
  NOT_FOUND: {
    label: 'NOT FOUND',
    className: 'statusNotFound',
    icon: '?',
    description: 'No record found. NOT the same as INVALID or FORGED.',
  },
  MISMATCH: {
    label: 'MISMATCH',
    className: 'statusMismatch',
    icon: '≠',
    description: 'Record found but critical identity fields differ.',
  },
  REVOKED: {
    label: 'REVOKED',
    className: 'statusRevoked',
    icon: '✗',
    description: 'Registry reports document as revoked.',
  },
  SUSPENDED: {
    label: 'SUSPENDED',
    className: 'statusSuspended',
    icon: '!',
    description: 'Registry reports document as suspended.',
  },
  EXPIRED: {
    label: 'EXPIRED',
    className: 'statusExpired',
    icon: '⌛',
    description: 'Registry reports document as expired.',
  },
  INVALID: {
    label: 'INVALID',
    className: 'statusRevoked',
    icon: '✗',
    description: 'Registry considers the document structurally invalid.',
  },
  AMBIGUOUS: {
    label: 'AMBIGUOUS',
    className: 'statusWarn',
    icon: '~',
    description: 'Multiple registry records match; cannot disambiguate.',
  },
  UNAVAILABLE: {
    label: 'UNAVAILABLE',
    className: 'statusUnavailable',
    icon: '○',
    description: 'Registry provider is not reachable. Document was not checked.',
  },
  TIMEOUT: {
    label: 'TIMEOUT',
    className: 'statusUnavailable',
    icon: '○',
    description: 'Registry provider timed out. Document was not checked.',
  },
  AUTHENTICATION_ERROR: {
    label: 'AUTH ERROR',
    className: 'statusUnavailable',
    icon: '○',
    description: 'Registry authentication failed. Contact system administration.',
  },
  PROVIDER_ERROR: {
    label: 'PROVIDER ERROR',
    className: 'statusUnavailable',
    icon: '○',
    description: 'Registry provider error. Document could not be checked.',
  },
  INCONCLUSIVE: {
    label: 'INCONCLUSIVE',
    className: 'statusWarn',
    icon: '~',
    description: 'Insufficient comparable fields to determine a match.',
  },
};

const FIELD_LABELS = {
  document_number: 'Document Number',
  name: 'Full Name',
  date_of_birth: 'Date of Birth',
  nationality: 'Nationality',
  expiry_date: 'Expiry Date',
  issuing_authority: 'Issuing Authority',
  gender: 'Gender',
};

const FIELD_STATUS_CONFIG = {
  MATCH: { label: 'MATCH', className: 'fieldMatch' },
  MISMATCH: { label: 'MISMATCH', className: 'fieldMismatch' },
  MISSING_IN_REGISTRY: { label: 'NOT IN REG', className: 'fieldMissing' },
  MISSING_IN_DOCUMENT: { label: 'NOT IN DOC', className: 'fieldMissing' },
  NOT_COMPARED: { label: 'N/A', className: 'fieldNa' },
};

const SOURCE_TYPE_LABELS = {
  development_mock: 'Development Sandbox',
  sandbox: 'Test Sandbox',
  authorized_external: 'Authorized Registry',
};

// ── Helper functions ──────────────────────────────────────────────────────────

function getStatusConfig(statusKey) {
  return STATUS_CONFIG[statusKey] || {
    label: statusKey || 'UNKNOWN',
    className: 'statusWarn',
    icon: '?',
    description: 'Unknown registry status.',
  };
}

function getSourceTypeLabel(sourceType) {
  return SOURCE_TYPE_LABELS[sourceType] || sourceType || 'Unknown';
}

// ── Sub-components ────────────────────────────────────────────────────────────

function RegistryStatusBadge({ status }) {
  const config = getStatusConfig(status);
  return (
    <div className={`${styles.statusBadge} ${styles[config.className] || ''}`}>
      <span className={styles.statusIcon} aria-hidden="true">{config.icon}</span>
      <span className={styles.statusLabel}>{config.label}</span>
    </div>
  );
}

function FieldResultRow({ result }) {
  const fieldConfig = FIELD_STATUS_CONFIG[result.status] || { label: result.status, className: 'fieldNa' };
  const fieldLabel = FIELD_LABELS[result.field] || result.field;

  return (
    <div className={`${styles.fieldRow} ${result.is_critical ? styles.fieldCritical : ''}`}>
      <div className={styles.fieldLeft}>
        {result.is_critical && (
          <span className={styles.criticalDot} title="Critical field" aria-label="Critical field" />
        )}
        <span className={styles.fieldName}>{fieldLabel}</span>
      </div>
      <div className={styles.fieldValues}>
        <span className={styles.fieldValue} title="Document value">
          {result.document_value || '—'}
        </span>
        <span className={styles.fieldArrow} aria-hidden="true">→</span>
        <span className={styles.fieldValue} title="Registry value">
          {result.registry_value || '—'}
        </span>
      </div>
      <span className={`${styles.fieldStatusPill} ${styles[fieldConfig.className] || ''}`}>
        {fieldConfig.label}
      </span>
    </div>
  );
}

function EvidenceItem({ item }) {
  const severityClass = item.severity === 'critical' ? styles.evCritical
    : item.severity === 'warning' ? styles.evWarning
    : styles.evInfo;

  return (
    <div className={`${styles.evidenceItem} ${severityClass}`}>
      <span className={styles.evidenceSeverity}>
        {item.severity === 'critical' ? '●' : item.severity === 'warning' ? '◐' : '○'}
      </span>
      <span className={styles.evidenceText}>{item.description}</span>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function RegistryStatus() {
  const { session } = useVerification();
  const { registryDetail } = session;
  const [showFieldDetails, setShowFieldDetails] = useState(false);
  const [showEvidence, setShowEvidence] = useState(false);

  if (!registryDetail) {
    return null;
  }

  const regSummary = registryDetail.registry || {};
  const fieldResults = registryDetail.field_results || [];
  const evidence = registryDetail.evidence || [];
  const providerMeta = registryDetail.provider_metadata || {};
  const status = regSummary.status;
  const statusConfig = getStatusConfig(status);
  const sourceTypeLabel = getSourceTypeLabel(providerMeta.source_type);
  const isMockProvider = providerMeta.source_type === 'development_mock';

  const criticalResults = fieldResults.filter(r => r.is_critical);
  const secondaryResults = fieldResults.filter(r => !r.is_critical);

  // Filter out the disclaimer evidence from the main list for separate display
  const mainEvidence = evidence.filter(e => e.type !== 'provider_disclaimer');
  const hasFieldResults = fieldResults.length > 0;

  return (
    <div className={styles.container}>
      {/* Provider header */}
      <div className={styles.providerHeader}>
        <div className={styles.providerInfo}>
          <span className={styles.providerIcon} aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
              <circle cx="12" cy="10" r="3" />
            </svg>
          </span>
          <span className={styles.providerName}>{sourceTypeLabel}</span>
          {isMockProvider && (
            <span className={styles.mockBadge} title="This is a development sandbox — not a real government registry">
              SANDBOX
            </span>
          )}
        </div>
        {providerMeta.response_time_ms != null && (
          <span className={styles.responseTime}>
            {providerMeta.response_time_ms.toFixed(0)}ms
          </span>
        )}
      </div>

      {/* Status banner */}
      <div className={`${styles.statusBanner} ${styles[`banner_${statusConfig.className}`] || styles.bannerDefault}`}>
        <RegistryStatusBadge status={status} />
        <p className={styles.statusDescription}>{statusConfig.description}</p>
      </div>

      {/* Disclaimer for mock provider */}
      {isMockProvider && (
        <div className={styles.disclaimer}>
          <span className={styles.disclaimerIcon} aria-hidden="true">ℹ</span>
          <span className={styles.disclaimerText}>
            Development Sandbox — Simulated data only. Not a government registry.
          </span>
        </div>
      )}

      {/* Field comparison results */}
      {hasFieldResults && (
        <div className={styles.fieldsSection}>
          <button
            className={styles.toggleBtn}
            onClick={() => setShowFieldDetails(v => !v)}
            aria-expanded={showFieldDetails}
          >
            <span>Identity Field Comparison</span>
            <span className={styles.fieldCount}>
              {criticalResults.filter(r => r.status === 'MATCH').length}/{criticalResults.length} critical matched
            </span>
            <span className={`${styles.chevron} ${showFieldDetails ? styles.chevronOpen : ''}`} aria-hidden="true">
              ▾
            </span>
          </button>

          {showFieldDetails && (
            <div className={styles.fieldsList}>
              {criticalResults.length > 0 && (
                <div className={styles.fieldsGroup}>
                  <div className={styles.groupLabel}>
                    <span className={styles.criticalDot} aria-hidden="true" />
                    Critical Fields
                  </div>
                  {criticalResults.map(r => (
                    <FieldResultRow key={r.field} result={r} />
                  ))}
                </div>
              )}
              {secondaryResults.length > 0 && (
                <div className={styles.fieldsGroup}>
                  <div className={styles.groupLabel}>Secondary Fields</div>
                  {secondaryResults.map(r => (
                    <FieldResultRow key={r.field} result={r} />
                  ))}
                </div>
              )}
              <div className={styles.fieldLegend}>
                <span className={styles.legendDot} aria-hidden="true" />
                <span>Critical fields anchor identity verification</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Evidence items */}
      {mainEvidence.length > 0 && (
        <div className={styles.evidenceSection}>
          <button
            className={styles.toggleBtn}
            onClick={() => setShowEvidence(v => !v)}
            aria-expanded={showEvidence}
          >
            <span>Registry Evidence</span>
            <span className={`${styles.chevron} ${showEvidence ? styles.chevronOpen : ''}`} aria-hidden="true">
              ▾
            </span>
          </button>
          {showEvidence && (
            <div className={styles.evidenceList}>
              {mainEvidence.map((item, idx) => (
                <EvidenceItem key={idx} item={item} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
