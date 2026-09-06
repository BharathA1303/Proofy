/**
 * RecentVerificationsTable.jsx
 *
 * Bottom-left table of recent verifications matching the exact reference image:
 * Headers: #, Document Type, Document No., Traveler Name, Result, Risk Score, Time
 * Includes 'View All ➔' header link and colored status pills.
 */
import styles from './RecentVerificationsTable.module.css';

const RECENT_DATA = [
  {
    id: '001',
    docType: 'Passport',
    docNo: 'A12345678',
    name: 'JOHN DOE',
    result: 'Clear',
    resultClass: 'resultClear',
    riskScore: '12/100',
    riskClass: 'riskLow',
    time: '10:22 AM',
  },
  {
    id: '002',
    docType: 'Visa',
    docNo: 'V9876543',
    name: 'MARIA GARCIA',
    result: 'Needs Review',
    resultClass: 'resultReview',
    riskScore: '55/100',
    riskClass: 'riskMed',
    time: '10:18 AM',
  },
  {
    id: '003',
    docType: 'National ID',
    docNo: 'IND123456',
    name: 'RAJ KUMAR',
    result: 'High Risk',
    resultClass: 'resultRisk',
    riskScore: '87/100',
    riskClass: 'riskHigh',
    time: '10:12 AM',
  },
];

export default function RecentVerificationsTable() {
  return (
    <div className={styles.tableCard}>
      <div className={styles.cardHeader}>
        <div className={styles.titleGroup}>
          <div className={styles.iconCircle}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </div>
          <h2 className={styles.title}>Recent Verifications</h2>
        </div>
        <a href="#view-all" className={styles.viewAllLink} onClick={(e) => e.preventDefault()}>
          <span>View All</span>
          <span aria-hidden="true">➔</span>
        </a>
      </div>

      <div className={styles.tableWrapper}>
        <table className={styles.table} aria-label="Recent Document Verifications">
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Document Type</th>
              <th scope="col">Document No.</th>
              <th scope="col">Traveler Name</th>
              <th scope="col">Result</th>
              <th scope="col">Risk Score</th>
              <th scope="col">Time</th>
            </tr>
          </thead>
          <tbody>
            {RECENT_DATA.map((row) => (
              <tr key={row.id}>
                <td className={styles.colId}>{row.id}</td>
                <td className={styles.colType}>{row.docType}</td>
                <td className={styles.colDocNo}>{row.docNo}</td>
                <td className={styles.colName}>{row.name}</td>
                <td>
                  <span className={`${styles.resultBadge} ${styles[row.resultClass]}`}>
                    <span className={styles.statusDot} aria-hidden="true" />
                    <span>{row.result}</span>
                  </span>
                </td>
                <td>
                  <span className={`${styles.riskBadge} ${styles[row.riskClass]}`}>
                    {row.riskScore}
                  </span>
                </td>
                <td className={styles.colTime}>{row.time}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
