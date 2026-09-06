/**
 * SectionHeader.jsx
 *
 * Consistent section heading used across all workspace panels.
 * Keeps heading hierarchy clean and scannable.
 */
import styles from './SectionHeader.module.css';

/**
 * @param {{
 *   title: string,
 *   subtitle?: string,
 *   level?: 2 | 3 | 4,
 *   action?: React.ReactNode
 * }} props
 */
export default function SectionHeader({ title, subtitle, level = 3, action }) {
  const Tag = `h${level}`;

  return (
    <div className={styles.header}>
      <div className={styles.text}>
        <Tag className={styles.title}>{title}</Tag>
        {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
      </div>
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
}
