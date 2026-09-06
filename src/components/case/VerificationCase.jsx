/**
 * VerificationCase.jsx
 *
 * Master Case Workspace for Multi-Document Verification and Cross-Document Intelligence.
 * Coordinates case lifecycle, document attachments, relationship inspection,
 * and composite risk assessment.
 */
import React, { useState, useEffect, useCallback } from 'react';
import styles from './CaseWorkspace.module.css';
import CaseDocuments from './CaseDocuments.jsx';
import AddDocumentModal from './AddDocumentModal.jsx';
import CrossDocumentPanel from './CrossDocumentPanel.jsx';
import CaseRiskSummary from './CaseRiskSummary.jsx';
import EvidenceIntegrityPanel from './EvidenceIntegrityPanel.jsx';
import OfficerDecisionPanel from './OfficerDecisionPanel.jsx';
import {
  createCase,
  addDocumentToCase,
  removeDocumentFromCase,
  evaluateCase,
  computeCaseRisk,
} from '../../services/caseApi.js';

export default function VerificationCase() {
  const [caseData, setCaseData] = useState(null);
  const [activeDocumentId, setActiveDocumentId] = useState(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Initialize fresh case on demand
  const handleNewCase = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const newCase = await createCase('Standard Border Control Multi-Document Case');
      setCaseData(newCase);
      setActiveDocumentId(null);
    } catch (err) {
      setError(err.message || 'Failed to initialize verification case');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let ignore = false;
    async function setupInitialCase() {
      setLoading(true);
      setError(null);
      try {
        const newCase = await createCase('Standard Border Control Multi-Document Case');
        if (!ignore) {
          setCaseData(newCase);
          if (newCase.documents && newCase.documents.length > 0) {
            setActiveDocumentId(newCase.documents[0].document_id);
          }
        }
      } catch (err) {
        if (!ignore) {
          setError(err.message || 'Failed to initialize verification case');
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    }

    setupInitialCase();
    return () => {
      ignore = true;
    };
  }, []);

  // Add document handler
  const handleAddDocument = async ({ documentType, file, replace }) => {
    if (!caseData?.case_id) return;
    setLoading(true);
    setError(null);
    try {
      const updatedCase = await addDocumentToCase(
        caseData.case_id,
        documentType,
        file,
        replace
      );
      setCaseData(updatedCase);
      setIsModalOpen(false);
      // Select the newly added document
      const activeDocs = updatedCase.documents || [];
      if (activeDocs.length > 0) {
        setActiveDocumentId(activeDocs[activeDocs.length - 1].document_id);
      }
    } catch (err) {
      setError(err.message || 'Failed to attach document to case');
    } finally {
      setLoading(false);
    }
  };

  // Remove document handler
  const handleRemoveDocument = async (documentId) => {
    if (!caseData?.case_id) return;
    setLoading(true);
    setError(null);
    try {
      const updatedCase = await removeDocumentFromCase(caseData.case_id, documentId);
      setCaseData(updatedCase);
      const remainingDocs = updatedCase.documents || [];
      setActiveDocumentId(remainingDocs.length > 0 ? remainingDocs[0].document_id : null);
    } catch (err) {
      setError(err.message || 'Failed to remove document');
    } finally {
      setLoading(false);
    }
  };

  // Re-evaluate relationships
  const handleReevaluate = async () => {
    if (!caseData?.case_id) return;
    setLoading(true);
    setError(null);
    try {
      const updatedCase = await evaluateCase(caseData.case_id);
      setCaseData(updatedCase);
    } catch (err) {
      setError(err.message || 'Failed to re-evaluate relationships');
    } finally {
      setLoading(false);
    }
  };

  // Refresh case risk
  const handleRefreshRisk = async () => {
    if (!caseData?.case_id) return;
    setLoading(true);
    setError(null);
    try {
      const res = await computeCaseRisk(caseData.case_id);
      setCaseData((prev) => ({
        ...prev,
        risk_assessment: res.risk_assessment,
      }));
    } catch (err) {
      setError(err.message || 'Failed to refresh case risk');
    } finally {
      setLoading(false);
    }
  };

  const activeDoc = (caseData?.documents || []).find(
    (d) => d.document_id === activeDocumentId
  );

  return (
    <div className={styles.caseContainer} id="case-workspace-container">
      {/* Case Header */}
      <header className={styles.caseHeader}>
        <div className={styles.caseTitleGroup}>
          <div className={styles.caseBadge}>
            <span className={styles.caseId}>{caseData?.case_id || 'INITIALIZING...'}</span>
            <span className={styles.caseStatus}>{caseData?.status || 'ACTIVE'}</span>
          </div>
          <span className={styles.caseMeta}>
            Multi-Document Screening Case · {caseData?.documents?.length || 0} Document(s) Active
          </span>
        </div>

        <div className={styles.caseActions}>
          <button
            type="button"
            className={styles.btnSecondary}
            onClick={handleNewCase}
            disabled={loading}
            id="btn-new-case"
          >
            New Case
          </button>
        </div>
      </header>

      {/* Error alert */}
      {error && (
        <div
          style={{
            background: '#fef2f2',
            border: '1px solid #fecaca',
            color: '#b91c1c',
            padding: '0.75rem 1rem',
            borderRadius: '6px',
            fontSize: '0.875rem',
          }}
          role="alert"
        >
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Document List */}
      <CaseDocuments
        documents={caseData?.documents || []}
        activeDocumentId={activeDocumentId}
        onSelectDocument={setActiveDocumentId}
        onRemoveDocument={handleRemoveDocument}
        onOpenAddModal={() => setIsModalOpen(true)}
      />

      {/* Active Document Inspector Summary */}
      {activeDoc && (
        <div
          style={{
            background: '#ffffff',
            border: '1px solid #e2e8f0',
            borderRadius: '8px',
            padding: '1rem 1.5rem',
          }}
          id={`inspector-${activeDoc.document_id}`}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
            <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, color: '#0f172a', margin: 0 }}>
              Inspecting: {activeDoc.document_type.toUpperCase()} ({activeDoc.document_id})
            </h3>
            <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
              Verification ID: {activeDoc.verification_id}
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem', fontSize: '0.8125rem' }}>
            <div>
              <span style={{ color: '#64748b' }}>Document Number:</span>{' '}
              <strong style={{ fontFamily: 'monospace' }}>
                {activeDoc.traveler_summary?.document_number ||
                  activeDoc.traveler_summary?.docNumber ||
                  activeDoc.traveler_summary?.passport_number ||
                  '—'}
              </strong>
            </div>
            <div>
              <span style={{ color: '#64748b' }}>Name:</span>{' '}
              <strong>{activeDoc.traveler_summary?.name || '—'}</strong>
            </div>
            <div>
              <span style={{ color: '#64748b' }}>Date of Birth:</span>{' '}
              <strong>
                {activeDoc.traveler_summary?.date_of_birth || activeDoc.traveler_summary?.dob || '—'}
              </strong>
            </div>
            <div>
              <span style={{ color: '#64748b' }}>Nationality:</span>{' '}
              <strong>{activeDoc.traveler_summary?.nationality || '—'}</strong>
            </div>
          </div>
        </div>
      )}

      {/* Cross-Document Consistency Table */}
      <CrossDocumentPanel
        relationships={caseData?.relationships || []}
        onReevaluate={handleReevaluate}
        loading={loading}
      />

      {/* Composite Risk Summary */}
      <CaseRiskSummary
        riskAssessment={caseData?.risk_assessment}
        onRefreshRisk={handleRefreshRisk}
        loading={loading}
      />

      {/* Evidence Integrity & Blockchain Audit */}
      <EvidenceIntegrityPanel
        targetId={caseData?.case_id}
        initialAudit={caseData?.blockchain_audit}
      />

      {/* Officer Decision Support */}
      <OfficerDecisionPanel
        targetId={caseData?.case_id}
        riskAssessment={caseData?.risk_assessment}
        onDecisionRecorded={handleRefreshRisk}
      />

      {/* Modal for Document Attachment */}
      <AddDocumentModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onAddDocument={handleAddDocument}
        loading={loading}
      />
    </div>
  );
}
