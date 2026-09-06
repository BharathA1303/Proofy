/**
 * SystemStatusCard.jsx
 *
 * Bottom-right card showing service health telemetry matching the exact reference image:
 * Services: OCR Engine, Biometric Service, Forensic Analysis, Risk Engine, Database
 * Includes 'View Details ➔' header link and 'Online' badges.
 */
import styles from './SystemStatusCard.module.css';

const SERVICES = [
  { name: 'OCR Engine',        status: 'Online' },
  { name: 'Biometric Service', status: 'Online' },
  { name: 'Forensic Analysis', status: 'Online' },
  { name: 'Risk Engine',       status: 'Online' },
  { name: 'Database',          status: 'Online' },
];

export default function SystemStatusCard() {
  return (
    <div className={styles.statusCard}>
      <div className={styles.cardHeader}>
        <div className={styles.titleGroup}>
          <div className={styles.iconCircle}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </div>
          <h2 className={styles.title}>System Status</h2>
        </div>
        <a href="#details" className={styles.detailsLink} onClick={(e) => e.preventDefault()}>
          <span>View Details</span>
          <span aria-hidden="true">➔</span>
        </a>
      </div>

      <ul className={styles.serviceList} aria-label="Microservice Health Status">
        {SERVICES.map((srv) => (
          <li key={srv.name} className={styles.serviceItem}>
            <div className={styles.serviceNameGroup}>
              <span className={styles.greenDot} aria-hidden="true" />
              <span className={styles.serviceName}>{srv.name}</span>
            </div>
            <span className={styles.onlineBadge}>Online</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
