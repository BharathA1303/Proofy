/**
 * LoginPage.jsx
 *
 * Official Border Clearance Terminal — Officer Authentication Portal.
 * Features Neomorphic styling, credential validation, and Multi-Factor Authentication (MFA).
 */
import { useState, useRef, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../state/auth/useAuth.js';
import styles from './LoginPage.module.css';

export default function LoginPage() {
  const { initiateLogin, verifyMfa, quickDemoLogin, pendingMfa, cancelMfa } = useAuth();
  const navigate = useNavigate();

  const [identifier, setIdentifier] = useState('BPO-4819');
  const [password, setPassword] = useState('Meiyari@2026');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // 6-digit MFA state
  const [mfaDigits, setMfaDigits] = useState(['', '', '', '', '', '']);
  const digitRefs = useRef([]);

  // Auto-focus first digit when entering MFA mode
  useEffect(() => {
    if (pendingMfa) {
      setTimeout(() => digitRefs.current[0]?.focus(), 100);
    }
  }, [pendingMfa]);

  function handleCredentialSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      initiateLogin(identifier, password);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleDigitChange(index, val) {
    const char = val.slice(-1).replace(/\D/g, '');
    const newDigits = [...mfaDigits];
    newDigits[index] = char;
    setMfaDigits(newDigits);

    if (char && index < 5) {
      digitRefs.current[index + 1]?.focus();
    }
  }

  function handleDigitKeyDown(index, e) {
    if (e.key === 'Backspace' && !mfaDigits[index] && index > 0) {
      digitRefs.current[index - 1]?.focus();
    }
  }

  function handleDigitPaste(e) {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
    if (!pasted) return;

    const newDigits = [...mfaDigits];
    for (let i = 0; i < 6; i++) {
      newDigits[i] = pasted[i] || '';
    }
    setMfaDigits(newDigits);
    const nextEmpty = newDigits.findIndex((d) => !d);
    const focusIdx = nextEmpty === -1 ? 5 : nextEmpty;
    digitRefs.current[focusIdx]?.focus();
  }

  function handleMfaSubmit(e) {
    e?.preventDefault();
    setError('');
    const fullCode = mfaDigits.join('');

    try {
      verifyMfa(fullCode);
      navigate('/');
    } catch (err) {
      setError(err.message);
    }
  }

  function handleQuickFillMfa() {
    const hint = pendingMfa?.mfaCodeHint || '614920';
    const digits = hint.split('');
    setMfaDigits(digits);
    setError('');
    try {
      verifyMfa(hint);
      navigate('/');
    } catch (err) {
      setError(err.message);
    }
  }

  function handleQuickDemo() {
    quickDemoLogin();
    navigate('/');
  }

  return (
    <div className={styles.loginRoot}>
      <div className={styles.terminalCard}>
        {/* Brand Header */}
        <div className={styles.headerSection}>
          <div className={styles.logoBadge}>
            <img src="/meiyari-mark.png" alt="Meiyari Shield" className={styles.logoImg} />
          </div>
          <span className={styles.eyebrow}>NATIONAL BORDER CLEARANCE SYSTEM</span>
          <h1 className={styles.terminalTitle}>MEIYARI TERMINAL</h1>
          <p className={styles.terminalSubtitle}>
            {pendingMfa
              ? 'Multi-Factor Identity Challenge (Step 2 of 2)'
              : 'Official Border Inspection & Identity Authentication'}
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

        {/* Step 1: Officer Credentials */}
        {!pendingMfa ? (
          <form className={styles.authForm} onSubmit={handleCredentialSubmit}>
            <div className={styles.formGroup}>
              <label className={styles.inputLabel} htmlFor="officerId">
                Officer ID / Official Email
              </label>
              <div className={styles.inputWell}>
                <span className={styles.inputIcon}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                    <circle cx="12" cy="7" r="4" />
                  </svg>
                </span>
                <input
                  id="officerId"
                  type="text"
                  className={styles.textInput}
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  placeholder="e.g. BPO-4819"
                  required
                  autoFocus
                />
              </div>
            </div>

            <div className={styles.formGroup}>
              <div className={styles.labelRow}>
                <label className={styles.inputLabel} htmlFor="password">
                  Security Passkey
                </label>
              </div>
              <div className={styles.inputWell}>
                <span className={styles.inputIcon}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                  </svg>
                </span>
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  className={styles.textInput}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  required
                />
                <button
                  type="button"
                  className={styles.passwordToggle}
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                      <line x1="1" y1="1" x2="23" y2="23" />
                    </svg>
                  ) : (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            <button type="submit" className={styles.primaryBtn} disabled={loading}>
              <span>Authenticate &amp; Request MFA Token</span>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="5" y1="12" x2="19" y2="12" />
                <polyline points="12 5 19 12 12 19" />
              </svg>
            </button>

            <button type="button" className={styles.quickDemoBtn} onClick={handleQuickDemo}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
              </svg>
              <span>1-Click Quick Demo Sign-in</span>
            </button>
          </form>
        ) : (
          /* Step 2: MFA Token Verification */
          <div className={styles.mfaBox}>
            <div className={styles.mfaNotice}>
              <strong>Officer Identity Challenge:</strong> Enter the 6-digit TOTP security code from your authorized authentication device.
            </div>

            <div className={styles.digitRow} onPaste={handleDigitPaste}>
              {mfaDigits.map((digit, idx) => (
                <input
                  key={idx}
                  ref={(el) => (digitRefs.current[idx] = el)}
                  type="text"
                  maxLength={1}
                  className={styles.digitInput}
                  value={digit}
                  onChange={(e) => handleDigitChange(idx, e.target.value)}
                  onKeyDown={(e) => handleDigitKeyDown(idx, e)}
                  autoComplete="off"
                />
              ))}
            </div>

            <button type="button" className={styles.mfaHintBtn} onClick={handleQuickFillMfa}>
              ⚡ Quick Fill Test Token (614920)
            </button>

            <button type="button" className={styles.primaryBtn} onClick={handleMfaSubmit}>
              <span>Verify Token &amp; Open Portal</span>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </button>

            <button
              type="button"
              className={styles.quickDemoBtn}
              onClick={() => {
                cancelMfa();
                setMfaDigits(['', '', '', '', '', '']);
              }}
            >
              ← Back to Credentials
            </button>
          </div>
        )}

        {/* Footer info */}
        <div className={styles.footerRow}>
          <span>Need terminal clearance?</span>
          <Link to="/register" className={styles.footerLink}>
            Provision Officer Station →
          </Link>
        </div>
      </div>
    </div>
  );
}
