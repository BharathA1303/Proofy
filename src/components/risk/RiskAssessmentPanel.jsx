// src/components/risk/RiskAssessmentPanel.jsx
//
// Module 6: Risk Engine & Officer Decision Support panel.
//
// CRITICAL UI CONTRACT:
//   - Never display "approved", "denied", "forged", "authentic", "cleared",
//     or any verdict vocabulary.
//   - Always display the advisory disclaimer below the recommendation.
//   - Risk score is labeled "Evidence Score" to avoid probabilistic
//     misinterpretation.
//   - Officer recommendation is labeled "Officer Review Guidance" not "Decision".

import { useState } from 'react';
import styles from './RiskAssessmentPanel.module.css';


// ── Helpers ──────────────────────────────────────────────────────────────────

const LEVEL_CLASS = {
  LOW:      styles.levelLow,
  MEDIUM:   styles.levelMedium,
  HIGH:     styles.levelHigh,
  CRITICAL: styles.levelCritical,
};

const LEVEL_ICON = {
  LOW:      '✓',
  MEDIUM:   '⚠',
  HIGH:     '⚠',
  CRITICAL: '⛔',
};

const SEVERITY_CLASS = {
  CRITICAL: styles.severityCritical,
  HIGH:     styles.severityHigh,
  MEDIUM:   styles.severityMedium,
  LOW:      styles.severityLow,
};

const BAR_CLASS_BY_LEVEL = {
  LOW:      styles.barLow,
  MEDIUM:   styles.barMedium,
  HIGH:     styles.barHigh,
  CRITICAL: styles.barCritical,
};

function arcColor(level) {
  return {
    LOW:      'hsl(142, 50%, 48%)',
    MEDIUM:   'hsl(38, 85%, 52%)',
    HIGH:     'hsl(18, 80%, 52%)',
    CRITICAL: 'hsl(355, 70%, 55%)',
  }[level] || 'hsl(205, 60%, 55%)';
}

function moduleStatusClass(status) {
  return {
    completed:   styles.moduleCompleted,
    partial:     styles.modulePartial,
    unavailable: styles.moduleUnavailable,
    not_run:     styles.moduleNotRun,
  }[status] || styles.moduleNotRun;
}

function moduleDotClass(status) {
  return {
    completed:   styles.dotCompleted,
    partial:     styles.dotPartial,
    unavailable: styles.dotUnavailable,
    not_run:     styles.dotNotRun,
  }[status] || styles.dotNotRun;
}


// ── Sub-components ───────────────────────────────────────────────────────────

function ScoreArc({ score, level }) {
  const pct = `${score}%`;
  const color = arcColor(level);
  return (
    <div className={styles.scoreArc}
      style={{ background: `conic-gradient(${color} ${pct}, var(--color-border) ${pct})` }}>
      <div className={styles.scoreArcInner}>
        <span className={styles.scoreNumber}>{score}</span>
        <span className={styles.scoreMax}>/100</span>
      </div>
    </div>
  );
}

function ConflictBanner({ conflicts }) {
  if (!conflicts || conflicts.length === 0) return null;
  return (
    <div className={styles.conflictBanner} role="alert" aria-label="Contradictory evidence detected">
      <span className={styles.conflictIcon}>⚠</span>
      <div className={styles.conflictBody}>
        <div className={styles.conflictTitle}>
          Contradictory evidence detected — officer attention required
        </div>
        <div className={styles.conflictList}>
          {conflicts.map((c) => (
            <div key={c.conflict_id} className={styles.conflictDetail}>
              <div className={styles.conflictId}>{c.conflict_id}</div>
              <div className={styles.conflictDesc}>{c.description}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ReasonItem({ reason }) {
  const [expanded, setExpanded] = useState(false);
  const provKeys = Object.keys(reason.provenance || {}).filter(
    (k) => !['source', 'module'].includes(k)
  );

  return (
    <div
      className={styles.reasonItem}
      data-severity={reason.severity}
      onClick={() => setExpanded((v) => !v)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && setExpanded((v) => !v)}
      aria-expanded={expanded}
      id={`reason-${reason.reason_id}`}
    >
      <div className={styles.reasonHeader}>
        <span className={styles.reasonModule}>{reason.module}</span>
        <span className={`${styles.reasonSeverity} ${SEVERITY_CLASS[reason.severity] || ''}`}>
          {reason.severity}
        </span>
        <span className={styles.reasonContribution}>
          +{reason.contribution.toFixed(1)} pts
        </span>
      </div>
      <div className={styles.reasonExplanation}>{reason.explanation}</div>
      {expanded && provKeys.length > 0 && (
        <div className={styles.reasonDetail}>
          {provKeys.slice(0, 6).map((k) => (
            <div key={k} className={styles.reasonDetailItem}>
              <div className={styles.reasonDetailLabel}>{k}</div>
              <div className={styles.reasonDetailValue}>
                {String(reason.provenance[k] ?? '—')}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ModuleCompleteness({ moduleSummary }) {
  return (
    <div className={styles.moduleGrid}>
      {(moduleSummary || []).map((m) => (
        <div key={m.module_id}
          className={`${styles.moduleChip} ${moduleStatusClass(m.status)}`}
          title={`${m.label}: ${m.status} (${m.evidence_count} items)`}
        >
          <span className={`${styles.moduleDot} ${moduleDotClass(m.status)}`} />
          {m.module_id}
        </div>
      ))}
    </div>
  );
}

function CategoryBreakdown({ breakdown, level }) {
  if (!breakdown || breakdown.length === 0) return null;
  const active = breakdown.filter((c) => c.maximum > 0);
  return (
    <div className={styles.breakdownList}>
      {active.map((c) => (
        <div key={c.category} className={styles.breakdownRow}>
          <div className={styles.breakdownLabel} title={c.category}>{c.label}</div>
          <div className={styles.breakdownBarWrap}>
            <div
              className={`${styles.breakdownBar} ${BAR_CLASS_BY_LEVEL[level] || styles.barNeutral}`}
              style={{ width: `${c.percentage_of_max}%` }}
            />
          </div>
          <div className={styles.breakdownValue}>{c.contribution.toFixed(1)}</div>
        </div>
      ))}
    </div>
  );
}


// ── Main panel ───────────────────────────────────────────────────────────────

export default function RiskAssessmentPanel({ data, loading }) {
  if (loading) {
    return (
      <div className={styles.panel}>
        <div className={styles.placeholder}>Computing risk assessment…</div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className={styles.panel}>
        <div className={styles.placeholder}>
          Run all verification steps first, then click "Assess Risk".
        </div>
      </div>
    );
  }

  const ra = data.risk_assessment;
  const level = ra.risk_level;
  const completePct = Math.round(ra.completeness * 100);

  return (
    <div className={styles.panel} id="risk-assessment-panel" aria-label="Module 6 Risk Assessment">

      {/* ── Score Row ── */}
      <div className={styles.scoreRow}>
        <div className={styles.scoreDial}>
          <ScoreArc score={ra.risk_score} level={level} />
        </div>
        <div className={styles.scoreInfo}>
          <span className={`${styles.levelBadge} ${LEVEL_CLASS[level] || ''}`}>
            {LEVEL_ICON[level]} {level}
          </span>
          <div className={styles.recommendation}>
            Officer Review Guidance: {ra.officer_recommendation}
          </div>
          <div className={styles.completenessRow}>
            <span>Pipeline completeness</span>
            <div className={styles.completenessBar}>
              <div className={styles.completenessFill} style={{ width: `${completePct}%` }} />
            </div>
            <span>{completePct}%</span>
          </div>
        </div>
      </div>

      {/* ── Conflicts ── */}
      {ra.conflict_detected && (
        <ConflictBanner conflicts={ra.conflicts} />
      )}

      {/* ── Reasons ── */}
      {ra.reasons && ra.reasons.length > 0 && (
        <section aria-labelledby="reasons-title">
          <h4 className={styles.sectionTitle} id="reasons-title">
            Adverse Findings ({ra.reasons.length})
          </h4>
          <div className={styles.reasonsList}>
            {ra.reasons.map((r) => (
              <ReasonItem key={r.reason_id} reason={r} />
            ))}
          </div>
        </section>
      )}

      {/* ── Category Breakdown ── */}
      {ra.category_breakdown && ra.category_breakdown.some((c) => c.contribution > 0) && (
        <section aria-labelledby="breakdown-title">
          <h4 className={styles.sectionTitle} id="breakdown-title">Score Breakdown by Category</h4>
          <CategoryBreakdown breakdown={ra.category_breakdown} level={level} />
        </section>
      )}

      {/* ── Module Completeness ── */}
      <section aria-labelledby="modules-title">
        <h4 className={styles.sectionTitle} id="modules-title">Verification Modules</h4>
        <ModuleCompleteness moduleSummary={ra.module_summary} />
      </section>

      {/* ── Uncertainties ── */}
      {ra.uncertainties && ra.uncertainties.length > 0 && (
        <section aria-labelledby="uncertainty-title">
          <h4 className={styles.sectionTitle} id="uncertainty-title">
            High-Severity Uncertain Findings
          </h4>
          {ra.uncertainties.map((u, i) => (
            <div key={i} className={styles.uncertaintyItem}>
              <span className={styles.uncertaintyIcon}>ℹ</span>
              <span>
                [{u.module}] {u.explanation}
                {' '}(confidence: {Math.round(u.confidence * 100)}%)
              </span>
            </div>
          ))}
        </section>
      )}

      {/* ── Advisory Disclaimer ── */}
      <div className={styles.advisory} role="note" aria-label="Advisory disclaimer">
        <span className={styles.advisoryIcon}>ℹ</span>
        <span>
          <strong>Advisory only.</strong> This risk assessment provides evidence-based
          guidance for the authorized officer. The evidence score is not a probability
          of fraud. The final decision on any traveler rests solely with the authorized
          officer and applicable law.
        </span>
      </div>
    </div>
  );
}
