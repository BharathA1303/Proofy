/**
 * StatusBadge.jsx
 *
 * Displays a verification check status with high-precision status dot and label.
 * Telemetry styling with glowing status dot.
 *
 * status values: 'pending' | 'passed' | 'failed' | 'warning' | 'skipped'
 */
import styles from './StatusBadge.module.css';

const STATUS_CONFIG = {
  pending: {
    label:     'Pending',
    className: styles.pending,
    ariaLabel: 'Status: Pending',
  },
  running: {
    label:     'Running',
    className: styles.running,
    ariaLabel: 'Status: Running',
  },
  completed: {
    label:     'Completed',
    className: styles.completed,
    ariaLabel: 'Status: Completed',
  },
  ready: {
    label:     'Ready',
    className: styles.ready,
    ariaLabel: 'Status: Ready',
  },
  passed: {
    label:     'Passed',
    className: styles.passed,
    ariaLabel: 'Status: Passed',
  },
  failed: {
    label:     'Failed',
    className: styles.failed,
    ariaLabel: 'Status: Failed',
  },
  warning: {
    label:     'Review',
    className: styles.warning,
    ariaLabel: 'Status: Requires Review',
  },
  skipped: {
    label:     'Skipped',
    className: styles.skipped,
    ariaLabel: 'Status: Skipped',
  },
  not_applicable: {
    label:     'Not Applicable',
    className: styles.notApplicable,
    ariaLabel: 'Status: Not Applicable',
  },
  unavailable: {
    label:     'Unavailable',
    className: styles.unavailable,
    ariaLabel: 'Status: Unavailable',
  },
};

/**
 * @param {{ status: string, showLabel?: boolean, size?: 'sm' | 'md' }} props
 */
export default function StatusBadge({ status, showLabel = true, size = 'md' }) {
  const normKey = (status || '').toLowerCase().replace(/[\s-]/g, '_');
  const config = STATUS_CONFIG[normKey] ?? STATUS_CONFIG.pending;

  return (
    <span
      className={`${styles.badge} ${config.className} ${styles[size]}`}
      aria-label={config.ariaLabel}
      role="status"
    >
      <span className={styles.dot} aria-hidden="true" />
      {showLabel && <span className={styles.label}>{config.label}</span>}
    </span>
  );
}

