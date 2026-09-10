/**
 * RegisterPage.jsx
 *
 * Officer Provisioning & Terminal Registration Portal.
 * Features Neomorphic styling and MFA enrollment verification.
 */
import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../state/auth/useAuth.js';
import styles from './RegisterPage.module.css';

export default function RegisterPage() {
  const { registerOfficer, verifyMfa, pendingMfa } = useAuth();
  const navigate = useNavigate();

  const [formData, setFormData] = useState({
    fullName: '',
    badgeId: '',
    email: '',
    station: 'Terminal 3 · Checkpoint Gate 4',
    password: '',
  });

  const [mfaToken, setMfaToken] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  function handleChange(field, value) {
    setFormData((prev) => ({ ...prev, [field]: value }));
  }

  function handleRegisterSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      registerOfficer(formData);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleMfaSubmit(e) {
    e.preventDefault();
    setError('');

    try {
      verifyMfa(mfaToken || '614920');
      navigate('/');
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className={styles.loginRoot}>
      <div className={styles.terminalCard}>
        <div className={styles.headerSection}>
          <div className={styles.logoBadge}>
            <img src="/meiyari-mark.png" alt="Meiyari Shield" className={styles.logoImg} />
          </div>
          <span className={styles.eyebrow}>PROVISIONING &amp; ENROLLMENT</span>
          <h1 className={styles.terminalTitle}>OFFICER REGISTRATION</h1>
          <p className={styles.terminalSubtitle}>
            {pendingMfa
              ? 'Complete Security Device Pairing (Step 2 of 2)'
              : 'Provision a New Border Inspection Station Credential'}
          </p>
        </div>

        {error && (
          <div className={styles.errorAlert || styles.errorBanner} role="alert">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>{error}</span>
          </div>
        )}

        {!pendingMfa ? (
          <form className={styles.authForm} onSubmit={handleRegisterSubmit}>
            <div className={styles.fieldRow}>
              <div className={styles.formGroup}>
                <label className={styles.inputLabel}>Full Name</label>
                <div className={styles.inputWell}>
                  <input
                    type="text"
                    className={styles.textInput}
                    placeholder="e.g. Insp. Vikram Singh"
                    value={formData.fullName}
                    onChange={(e) => handleChange('fullName', e.target.value)}
                    required
                  />
                </div>
              </div>

              <div className={styles.formGroup}>
                <label className={styles.inputLabel}>Badge / Officer ID</label>
                <div className={styles.inputWell}>
                  <input
                    type="text"
                    className={styles.textInput}
                    placeholder="e.g. BPO-9021"
                    value={formData.badgeId}
                    onChange={(e) => handleChange('badgeId', e.target.value)}
                    required
                  />
                </div>
              </div>
            </div>

            <div className={styles.formGroup}>
              <label className={styles.inputLabel}>Government Duty Email</label>
              <div className={styles.inputWell}>
                <input
                  type="email"
                  className={styles.textInput}
                  placeholder="officer@bordercontrol.gov.in"
                  value={formData.email}
                  onChange={(e) => handleChange('email', e.target.value)}
                  required
                />
              </div>
            </div>

            <div className={styles.formGroup}>
              <label className={styles.inputLabel}>Assigned Border Station</label>
              <div className={styles.inputWell}>
                <input
                  type="text"
                  className={styles.textInput}
                  value={formData.station}
                  onChange={(e) => handleChange('station', e.target.value)}
                  required
                />
              </div>
            </div>

            <div className={styles.formGroup}>
              <label className={styles.inputLabel}>Security Passkey</label>
              <div className={styles.inputWell}>
                <input
                  type="password"
                  className={styles.textInput}
                  placeholder="Minimum 6 characters"
                  value={formData.password}
                  onChange={(e) => handleChange('password', e.target.value)}
                  required
                />
              </div>
            </div>

            <button type="submit" className={styles.primaryBtn} disabled={loading}>
              <span>Pair Security Token &amp; Proceed</span>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="5" y1="12" x2="19" y2="12" />
                <polyline points="12 5 19 12 12 19" />
              </svg>
            </button>
          </form>
        ) : (
          <form className={styles.mfaBox} onSubmit={handleMfaSubmit}>
            <div className={styles.mfaNotice}>
              <strong>Security Key Provisioned:</strong> Verify enrollment by confirming the 6-digit cryptographic TOTP token from your authenticator.
            </div>

            <div className={styles.formGroup}>
              <label className={styles.inputLabel}>6-Digit Security Token</label>
              <div className={styles.inputWell}>
                <input
                  type="text"
                  maxLength={6}
                  className={styles.textInput}
                  placeholder="e.g. 614920"
                  value={mfaToken}
                  onChange={(e) => setMfaToken(e.target.value.replace(/\D/g, ''))}
                  autoFocus
                  required
                />
              </div>
            </div>

            <button
              type="button"
              className={styles.mfaHintBtn}
              onClick={() => setMfaToken('614920')}
            >
              ⚡ Use Test Token (614920)
            </button>

            <button type="submit" className={styles.primaryBtn}>
              <span>Confirm Enrollment &amp; Launch Terminal</span>
            </button>
          </form>
        )}

        <div className={styles.footerRow}>
          <span>Already authorized?</span>
          <Link to="/login" className={styles.footerLink}>
            Officer Login →
          </Link>
        </div>
      </div>
    </div>
  );
}
