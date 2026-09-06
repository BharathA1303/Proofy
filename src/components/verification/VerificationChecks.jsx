/**
 * VerificationChecks.jsx
 *
 * Renders the sequence of security inspection modules for border screening.
 * Each module shows:
 *   - Module identifier tag (M1–M5 / REG / RISK)
 *   - Primary check title & algorithmic description
 *   - Telemetry status badge (Pending, Passed, Review, Failed)
 *
 * Phase 2 Enhancement:
 * When Module 2 (Document Validation) completes, it expands to show detailed
 * ICAO Doc 9303 checksum evidence, TD3 structural format, date verification,
 * and the Passport Number Binding Trap cross-check (VIZ <-> MRZ).
 */
import { useState } from 'react';
import { useVerification } from '../../state/verification/useVerification.js';
import { getProfile } from '../../config/documentProfiles.js';
import StatusBadge from '../common/StatusBadge.jsx';
import SectionHeader from '../common/SectionHeader.jsx';
import RegistryStatus from '../registry/RegistryStatus.jsx';
import RiskAssessmentPanel from '../risk/RiskAssessmentPanel.jsx';
import styles from './VerificationChecks.module.css';

const CHECK_METADATA = {
  documentValidation: {
    tag: 'M1/M2',
    description: 'ICAO Doc 9303 checksums & VIZ document structure',
  },
  tamperingDetection: {
    tag: 'M3',
    description: 'Error Level Analysis & photo boundary forensics',
  },
  faceVerification: {
    tag: 'M4',
    description: 'ArcFace biometric vector & 3D liveness match',
  },
  registryVerification: {
    tag: 'M5',
    description: 'Generic registry engine — development sandbox mode',
  },
  riskAssessment: {
    tag: 'RISK',
    description: 'Dynamic threat scoring & composite risk matrix',
  },
};

const SIGNAL_LABELS = {
  ela: 'Error Level Analysis',
  photo_boundary: 'Photo Boundary',
  compression: 'Compression Analysis',
  metadata: 'Metadata',
};

const BIOMETRIC_BADGE_CLASS = {
  FACE_MATCH: 'passed',
  FACE_MISMATCH: 'failed',
  SUSPECTED_SPOOF: 'failed',
  DOCUMENT_FACE_UNAVAILABLE: 'warning',
  LIVE_FACE_UNAVAILABLE: 'warning',
  FACE_VERIFICATION_INCONCLUSIVE: 'warning',
  MODEL_UNAVAILABLE: 'insufficient_data',
  PROCESSING_ERROR: 'failed',
};

// Reuses the existing validationBadge palette (passed/warning/failed/insufficient_data)
// for the Module 3 overall_assessment badge.
const FORENSIC_BADGE_CLASS = {
  no_significant_anomaly: 'passed',
  suspicious: 'warning',
  high_forensic_concern: 'failed',
  insufficient_data: 'insufficient_data',
};

const CHECK_TITLES = {
  mrz_structure: 'MRZ TD3 Structure',
  document_number_checksum: 'Document No. Checksum',
  dob_checksum: 'Date of Birth Checksum',
  expiry_checksum: 'Expiry Date Checksum',
  composite_checksum: 'Composite Checksum',
  expiry_date: 'Document Validity Period',
  passport_number_binding: 'Passport Number Binding Trap',
  viz_mrz_consistency: 'Cross-Field Alignment (VIZ ↔ MRZ)',
  required_fields: 'Required Field Presence',
  date_chronology: 'Date Chronology Integrity',
  visa_number_format: 'Visa Number Format',
  passport_reference: 'Passport Reference Cross-Check',
  field_consistency: 'Field Consistency',
  license_number_format: 'License Number Format',
  age_eligibility: 'Driver Age Eligibility',
  id_format: 'National ID Format',
  verhoeff_checksum: 'Verhoeff Checksum (Dihedral D5)',
  date_validity: 'Date / Age Validity',
  qr_consistency: 'Secure QR Code Consistency',
  permit_format: 'Border Permit Format',
  validity_period: 'Permit Validity Period',
  passport_binding: 'Border Permit ↔ Passport Binding',
  entry_exit_rules: 'Entry / Exit Port Clearance',
};

export default function VerificationChecks() {
  const { session } = useVerification();
  const profile = getProfile(session.documentType);
  const [evidenceOpen, setEvidenceOpen] = useState(true);
  // Module 3 evidence is collapsed by default (spec requirement) —
  // separate from Module 2's evidence toggle above.
  const [forensicEvidenceOpen, setForensicEvidenceOpen] = useState(false);
  const [faceEvidenceOpen, setFaceEvidenceOpen] = useState(false);
  const [registryEvidenceOpen, setRegistryEvidenceOpen] = useState(false);
  const [riskPanelOpen, setRiskPanelOpen] = useState(true);

  const valDetail = session.validationDetail;
  const hasValidationDetail = Boolean(valDetail && valDetail.checks);

  const forensicDetail = session.forensicDetail;
  const hasForensicDetail = Boolean(forensicDetail);

  const faceDetail = session.faceDetail;
  const hasFaceDetail = Boolean(faceDetail && faceDetail.document_face);

  const registryDetail = session.registryDetail;
  const hasRegistryDetail = Boolean(registryDetail);

  const riskData = session.risk?.data ?? null;
  const riskLoading = session.risk?.loading ?? false;
  const hasRiskData = Boolean(riskData) || riskLoading;

  return (
    <div className={styles.section} aria-label="Pipeline verification checks">
      <SectionHeader
        title="Inspection Pipeline Modules"
        subtitle="Autonomous credential validation pipeline"
        level={3}
      />

      <ul className={styles.checkList} aria-label="Individual check results">
        {profile.verificationChecks.map((check) => {
          const status = session.checks[check.key] ?? 'pending';
          const meta = CHECK_METADATA[check.key] ?? { tag: 'MOD', description: 'Inspection check' };
          const isDocVal = check.key === 'documentValidation';
          const isTampering = check.key === 'tamperingDetection';
          const isFace = check.key === 'faceVerification';
          const isRegistry = check.key === 'registryVerification';
          const isRisk = check.key === 'riskAssessment';

          return (
            <li key={check.key} className={`${styles.checkItem} ${(isDocVal && hasValidationDetail) || (isTampering && hasForensicDetail) || (isFace && hasFaceDetail) || (isRegistry && hasRegistryDetail) || (isRisk && hasRiskData) ? styles.checkItemExpanded : ''}`}>
              <div className={styles.itemHeader}>
                <div className={styles.moduleInfo}>
                  <span className={styles.moduleTag} aria-hidden="true">{meta.tag}</span>
                  <div className={styles.moduleText}>
                    <span className={styles.checkLabel}>{check.label}</span>
                    <span className={styles.checkDesc}>{meta.description}</span>
                  </div>
                </div>
                <div className={styles.statusGroup}>
                  <StatusBadge status={status} />
                  {isFace && hasFaceDetail && (
                    <button
                      type="button"
                      className={styles.expandButton}
                      onClick={() => setFaceEvidenceOpen((prev) => !prev)}
                      aria-expanded={faceEvidenceOpen}
                      aria-label="Toggle biometric evidence panel"
                    >
                      <svg
                        className={`${styles.chevron} ${faceEvidenceOpen ? styles.chevronOpen : ''}`}
                        width="16"
                        height="16"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <polyline points="6 9 12 15 18 9" />
                      </svg>
                    </button>
                  )}
                  {isRegistry && hasRegistryDetail && (
                    <button
                      type="button"
                      className={styles.expandButton}
                      onClick={() => setRegistryEvidenceOpen((prev) => !prev)}
                      aria-expanded={registryEvidenceOpen}
                      aria-label="Toggle registry evidence panel"
                    >
                      <svg
                        className={`${styles.chevron} ${registryEvidenceOpen ? styles.chevronOpen : ''}`}
                        width="16"
                        height="16"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <polyline points="6 9 12 15 18 9" />
                      </svg>
                    </button>
                  )}
                  {isRisk && hasRiskData && (
                    <button
                      type="button"
                      className={styles.expandButton}
                      onClick={() => setRiskPanelOpen((prev) => !prev)}
                      aria-expanded={riskPanelOpen}
                      aria-label="Toggle risk assessment panel"
                    >
                      <svg
                        className={`${styles.chevron} ${riskPanelOpen ? styles.chevronOpen : ''}`}
                        width="16" height="16" viewBox="0 0 24 24"
                        fill="none" stroke="currentColor" strokeWidth="2"
                        strokeLinecap="round" strokeLinejoin="round"
                      >
                        <polyline points="6 9 12 15 18 9" />
                      </svg>
                    </button>
                  )}
                  {isTampering && hasForensicDetail && (

                    <button
                      type="button"
                      className={styles.expandButton}
                      onClick={() => setForensicEvidenceOpen((prev) => !prev)}
                      aria-expanded={forensicEvidenceOpen}
                      aria-label="Toggle forensic evidence panel"
                    >
                      <svg
                        className={`${styles.chevron} ${forensicEvidenceOpen ? styles.chevronOpen : ''}`}
                        width="16"
                        height="16"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <polyline points="6 9 12 15 18 9" />
                      </svg>
                    </button>
                  )}
                  {isDocVal && hasValidationDetail && (
                    <button
                      type="button"
                      className={styles.expandButton}
                      onClick={() => setEvidenceOpen((prev) => !prev)}
                      aria-expanded={evidenceOpen}
                      aria-label="Toggle validation evidence panel"
                    >
                      <svg
                        className={`${styles.chevron} ${evidenceOpen ? styles.chevronOpen : ''}`}
                        width="16"
                        height="16"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <polyline points="6 9 12 15 18 9" />
                      </svg>
                    </button>
                  )}
                </div>
              </div>

              {/* Module 2 Inspection Evidence Breakdown */}
              {isDocVal && hasValidationDetail && evidenceOpen && (
                <div className={styles.evidencePanel} aria-label="Algorithmic Verification Breakdown">
                  <div className={styles.evidenceHeader}>
                    <span className={styles.evidenceTitle}>Module 2: Algorithmic Verification Breakdown</span>
                    <span className={`${styles.validationBadge} ${styles[valDetail.status] || ''}`}>
                      {(valDetail.status || 'unknown').toUpperCase()}
                    </span>
                  </div>

                  <p className={styles.evidenceSummary}>{valDetail.summary || 'Document validation completed.'}</p>

                  <div className={styles.subCheckGrid}>
                    {Object.entries(valDetail.checks || {}).map(([checkKey, checkItem]) => {
                      if (!checkItem || typeof checkItem !== 'object') return null;

                      // Cross-zone consistency dictionary is rendered separately below
                      if (checkKey === 'viz_mrz_consistency') return null;

                      // Passport Number Binding Trap
                      if (checkKey === 'passport_number_binding') {
                        const isMatch = checkItem.match === true;
                        const isMismatch = checkItem.match === false;
                        return (
                          <div key={checkKey} className={`${styles.subCheckRow} ${styles.bindingRow}`}>
                            <div className={styles.bindingHeader}>
                              <span className={styles.subCheckName}>Passport Number Binding Trap</span>
                              <span className={styles.trapPill}>CRITICAL VIZ ↔ MRZ</span>
                            </div>
                            <span className={styles.subCheckDesc}>{checkItem.message || 'Passport number consistency'}</span>
                            <span className={`${styles.miniPill} ${isMatch ? styles.pillPass : (isMismatch ? styles.pillFail : styles.pillWarn)}`}>
                              {isMatch ? 'BOUND' : (isMismatch ? 'MISMATCH' : (checkItem.status ? String(checkItem.status).toUpperCase() : 'UNKNOWN'))}
                            </span>
                          </div>
                        );
                      }

                      // Checksums with computed / actual digits
                      if (checkItem.computed !== undefined) {
                        const isPass = checkItem.valid === true || checkItem.status === 'passed';
                        return (
                          <div key={checkKey} className={styles.subCheckRow}>
                            <span className={styles.subCheckName}>
                              {CHECK_TITLES[checkKey] || checkKey.replace(/_/g, ' ')}
                            </span>
                            <span className={styles.subCheckDesc}>
                              Computed: <strong>{String(checkItem.computed)}</strong>
                              {checkItem.actual !== null && checkItem.actual !== undefined && (
                                <> | MRZ: <strong>{String(checkItem.actual)}</strong></>
                              )}
                            </span>
                            <span className={`${styles.miniPill} ${isPass ? styles.pillPass : styles.pillFail}`}>
                              {(checkItem.status || (isPass ? 'passed' : 'failed')).toUpperCase()}
                            </span>
                          </div>
                        );
                      }

                      // Expiry date validity check
                      if (checkKey === 'expiry_date') {
                        const isExpired = checkItem.expired === true;
                        const isValid = checkItem.valid === true && !isExpired;
                        return (
                          <div key={checkKey} className={styles.subCheckRow}>
                            <span className={styles.subCheckName}>Document Validity Period</span>
                            <span className={styles.subCheckDesc}>
                              {checkItem.message || (isExpired ? 'Document has expired' : 'Document within valid range')}
                            </span>
                            <span className={`${styles.miniPill} ${isValid ? styles.pillPass : styles.pillFail}`}>
                              {isExpired ? 'EXPIRED' : isValid ? 'VALID' : 'CHECK'}
                            </span>
                          </div>
                        );
                      }

                      // Generic Sub-check row for all document profiles (Visa, DL, National ID, Border Permit, MRZ TD3 structure, etc.)
                      const isPass = checkItem.valid === true || checkItem.status === 'passed' || checkItem.status === 'pass';
                      const isFail = checkItem.valid === false || checkItem.status === 'failed' || checkItem.status === 'fail';
                      const pillClass = isPass ? styles.pillPass : isFail ? styles.pillFail : styles.pillWarn;
                      const statusLabel = (checkItem.status || (isPass ? 'passed' : isFail ? 'failed' : 'unknown')).toUpperCase();

                      return (
                        <div key={checkKey} className={styles.subCheckRow}>
                          <span className={styles.subCheckName}>
                            {CHECK_TITLES[checkKey] || checkKey.replace(/_/g, ' ')}
                          </span>
                          <span className={styles.subCheckDesc}>
                            {checkItem.message || (typeof checkItem === 'string' ? checkItem : 'Check completed')}
                          </span>
                          <span className={`${styles.miniPill} ${pillClass}`}>
                            {statusLabel}
                          </span>
                        </div>
                      );
                    })}

                    {/* Cross-Zone Field Consistency */}
                    {valDetail.checks?.viz_mrz_consistency?.fields && (
                      <div className={styles.consistencySection}>
                        <span className={styles.consistencyTitle}>Cross-Field Alignment (VIZ ↔ MRZ):</span>
                        <div className={styles.consistencyTokens}>
                          {Object.entries(valDetail.checks.viz_mrz_consistency.fields).map(([fieldName, item]) => {
                            if (!item) return null;
                            const isMatch = item.match === true;
                            const isMismatch = item.match === false;
                            return (
                              <span
                                key={fieldName}
                                className={`${styles.fieldToken} ${isMatch ? styles.tokenMatch : (isMismatch ? styles.tokenMismatch : styles.tokenUnknown)}`}
                                title={item.message}
                              >
                                {fieldName.replace(/_/g, ' ')}: {(item.status || 'unknown').toUpperCase()}
                              </span>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Issues List (if any) */}
                  {Array.isArray(valDetail.issues) && valDetail.issues.length > 0 && (
                    <div className={styles.issuesContainer}>
                      <span className={styles.issuesTitle}>Detected Inspection Issues ({valDetail.issues.length}):</span>
                      <ul className={styles.issuesList}>
                        {valDetail.issues.map((issue, idx) => (
                          <li key={idx} className={`${styles.issueItem} ${styles['severity_' + issue.severity] || ''}`}>
                            <span className={styles.issueSeverity}>{(issue.severity || 'issue').toUpperCase()}</span>
                            <span className={styles.issueMsg}>{issue.message || ''}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* Module 3 Forensic Evidence Breakdown (collapsed by default) */}
              {isTampering && hasForensicDetail && forensicEvidenceOpen && (
                <div className={styles.evidencePanel} aria-label="Module 3 Forensic Evidence Breakdown">
                  <div className={styles.evidenceHeader}>
                    <span className={styles.evidenceTitle}>Module 3: Forensic Analysis Breakdown</span>
                    <span className={`${styles.validationBadge} ${styles[FORENSIC_BADGE_CLASS[forensicDetail.overall_assessment]] || ''}`}>
                      {(forensicDetail.overall_assessment || 'unknown').replace(/_/g, ' ').toUpperCase()}
                    </span>
                  </div>

                  <p className={styles.evidenceSummary}>{forensicDetail.explanation || ''}</p>

                  {forensicDetail.status === 'insufficient_data' ? (
                    <p className={styles.evidenceSummary}>
                      Forensic analysis was not completed: image quality was insufficient
                      for reliable results.
                    </p>
                  ) : (
                    <>
                      <div className={styles.subCheckGrid}>
                        {Array.isArray(forensicDetail.signals) && forensicDetail.signals.map((signal) => (
                          <div className={styles.subCheckRow} key={signal.type}>
                            <span className={styles.subCheckName}>
                              {SIGNAL_LABELS[signal.type] ?? signal.type}
                            </span>
                            <span className={styles.subCheckDesc}>{signal.description}</span>
                            <span
                              className={`${styles.miniPill} ${
                                signal.status === 'suspicious'
                                  ? styles.pillFail
                                  : (signal.status === 'unavailable' || signal.status === 'insufficient_data')
                                    ? styles.pillWarn
                                    : styles.pillPass
                              }`}
                            >
                              {(signal.status || 'unknown').replace(/_/g, ' ').toUpperCase()}
                            </span>
                          </div>
                        ))}
                      </div>

                      {forensicDetail.photo_region && (
                        <div className={styles.consistencySection}>
                          <span className={styles.consistencyTitle}>Potential anomaly region:</span>
                          <div className={styles.consistencyTokens}>
                            <span className={styles.fieldToken} title="Coordinates are relative to the original uploaded image">
                              x:{forensicDetail.photo_region.x} y:{forensicDetail.photo_region.y}{' '}
                              w:{forensicDetail.photo_region.width} h:{forensicDetail.photo_region.height}
                            </span>
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

              {/* Module 4 Biometric Telemetry Breakdown */}
              {isFace && hasFaceDetail && faceEvidenceOpen && (
                <div className={styles.evidencePanel} aria-label="Module 4 Biometric Telemetry Breakdown">
                  <div className={styles.evidenceHeader}>
                    <span className={styles.evidenceTitle}>Module 4: Biometric Telemetry Breakdown</span>
                    <span className={`${styles.validationBadge} ${styles[BIOMETRIC_BADGE_CLASS[faceDetail.overall_assessment] || 'warning']}`}>
                      {(faceDetail.overall_assessment || 'unknown').replace(/_/g, ' ').toUpperCase()}
                    </span>
                  </div>

                  <p className={styles.evidenceSummary}>{faceDetail.summary || 'Biometric analysis complete.'}</p>

                  <div className={styles.subCheckGrid}>
                    {/* Document Face Gate */}
                    {faceDetail.document_face && (
                      <div className={styles.subCheckRow}>
                        <span className={styles.subCheckName}>Document Photo Quality</span>
                        <span className={styles.subCheckDesc}>
                          {faceDetail.document_face.detected
                            ? `Face detected (${faceDetail.document_face.quality_details?.explanation || 'Quality acceptable'})`
                            : (faceDetail.document_face.error || 'No face detected on document')}
                        </span>
                        <span className={`${styles.miniPill} ${faceDetail.document_face.quality === 'acceptable' ? styles.pillPass : styles.pillFail}`}>
                          {(faceDetail.document_face.quality || 'unknown').toUpperCase()}
                        </span>
                      </div>
                    )}

                    {/* Live Camera Face Gate */}
                    {faceDetail.live_face && (
                      <div className={styles.subCheckRow}>
                        <span className={styles.subCheckName}>Live Subject Quality</span>
                        <span className={styles.subCheckDesc}>
                          {faceDetail.live_face.detected
                            ? `Live face detected (${faceDetail.live_face.quality_details?.explanation || 'Quality acceptable'})`
                            : (faceDetail.live_face.error || 'No live face detected')}
                        </span>
                        <span className={`${styles.miniPill} ${faceDetail.live_face.quality === 'acceptable' ? styles.pillPass : styles.pillFail}`}>
                          {(faceDetail.live_face.quality || 'unavailable').toUpperCase()}
                        </span>
                      </div>
                    )}

                    {/* Anti-Spoof / Presentation Attack Detection */}
                    {faceDetail.anti_spoof && (
                      <div className={styles.subCheckRow}>
                        <span className={styles.subCheckName}>
                          Presentation Attack Detection ({faceDetail.anti_spoof.model || 'MiniFASNetV2'})
                        </span>
                        <span className={styles.subCheckDesc}>
                          {faceDetail.anti_spoof.explanation || 'PAD analysis complete'}
                          {faceDetail.anti_spoof.score !== null && faceDetail.anti_spoof.score !== undefined && (
                            <> | Score: <strong>{Math.round(faceDetail.anti_spoof.score * 100)}%</strong></>
                          )}
                        </span>
                        <span className={`${styles.miniPill} ${faceDetail.anti_spoof.status === 'pass' ? styles.pillPass : (faceDetail.anti_spoof.status === 'suspected_spoof' ? styles.pillFail : styles.pillWarn)}`}>
                          {(faceDetail.anti_spoof.status || 'unknown').replace(/_/g, ' ').toUpperCase()}
                        </span>
                      </div>
                    )}

                    {/* Facial Vector Similarity Match */}
                    {faceDetail.face_match && (
                      <div className={styles.subCheckRow}>
                        <span className={styles.subCheckName}>
                          Facial Vector Match ({faceDetail.face_match.embedding_model ? `${faceDetail.face_match.embedding_model} 512-D` : 'ArcFace 512-D'})
                        </span>
                        <span className={styles.subCheckDesc}>
                          {faceDetail.face_match.explanation || 'Biometric match'}
                          {faceDetail.face_match.similarity !== null && faceDetail.face_match.similarity !== undefined && (
                            <> | Match: <strong>{Math.round(faceDetail.face_match.similarity * 100)}%</strong> (Threshold: <strong>{Math.round((faceDetail.face_match.threshold || 0.6) * 100)}%</strong>)</>
                          )}
                        </span>
                        <span className={`${styles.miniPill} ${faceDetail.face_match.status === 'match' ? styles.pillPass : (faceDetail.face_match.status === 'no_match' ? styles.pillFail : styles.pillWarn)}`}>
                          {(faceDetail.face_match.status || 'unknown').toUpperCase()}
                        </span>
                      </div>
                    )}

                    {/* Secondary Optical Defense Telemetry */}
                    {faceDetail.secondary_pad && (
                      <div className={styles.consistencySection}>
                        <span className={styles.consistencyTitle}>Secondary Optical Telemetry (Defensive Multi-Cue):</span>
                        <div className={styles.consistencyTokens}>
                          {faceDetail.secondary_pad.frequency_domain_score !== undefined && (
                            <span className={`${styles.fieldToken} ${faceDetail.secondary_pad.frequency_domain_score >= 0.70 ? styles.tokenMatch : styles.tokenMismatch}`}>
                              2D FFT Moiré: {Math.round(faceDetail.secondary_pad.frequency_domain_score * 100)}%
                            </span>
                          )}
                          {faceDetail.secondary_pad.color_texture_score !== undefined && (
                            <span className={`${styles.fieldToken} ${faceDetail.secondary_pad.color_texture_score >= 0.70 ? styles.tokenMatch : styles.tokenMismatch}`}>
                              Chroma / Texture: {Math.round(faceDetail.secondary_pad.color_texture_score * 100)}%
                            </span>
                          )}
                          {faceDetail.secondary_pad.specular_reflection_score !== undefined && (
                            <span className={`${styles.fieldToken} ${faceDetail.secondary_pad.specular_reflection_score >= 0.70 ? styles.tokenMatch : styles.tokenMismatch}`}>
                              Specular Glare: {Math.round(faceDetail.secondary_pad.specular_reflection_score * 100)}%
                            </span>
                          )}
                          {faceDetail.secondary_pad.temporal_variance_score !== null && faceDetail.secondary_pad.temporal_variance_score !== undefined && (
                            <span className={`${styles.fieldToken} ${faceDetail.secondary_pad.temporal_variance_score >= 0.70 ? styles.tokenMatch : styles.tokenMismatch}`}>
                              Temporal Variance: {Math.round(faceDetail.secondary_pad.temporal_variance_score * 100)}%
                            </span>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
              {/* Module 5 Registry Evidence Panel */}
              {isRegistry && hasRegistryDetail && registryEvidenceOpen && (
                <RegistryStatus />
              )}
              {/* Module 6 Risk Assessment Panel */}
              {isRisk && hasRiskData && riskPanelOpen && (
                <div className={styles.evidencePanel} aria-label="Module 6 Risk Assessment">
                  <RiskAssessmentPanel data={riskData ? { risk_assessment: riskData } : null} loading={riskLoading} />
                </div>
              )}
            </li>

          );
        })}
      </ul>
    </div>
  );
}
