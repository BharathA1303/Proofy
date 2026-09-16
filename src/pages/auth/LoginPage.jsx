/**
 * LoginPage.jsx
 *
 * Professional Enterprise Authentication Portal.
 * Features a modern split-screen hero showcase, standard login credentials,
 * tactile neomorphic controls, and Multi-Factor Authentication (TOTP).
 */
import { useState, useRef, useEffect } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { useAuth } from '../../state/auth/useAuth.js';
import styles from './LoginPage.module.css';

export default function LoginPage() {
  const { initiateLogin, verifyMfa, pendingMfa, cancelMfa } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Success notice if redirected from registration
  const successNotice = location.state?.registeredMessage || '';

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

  async function handleMfaSubmit(e) {
    e?.preventDefault();
    setError('');
    const fullCode = mfaDigits.join('');

    try {
      await verifyMfa(fullCode);
      navigate('/');
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className={styles.pageRoot}>
      {/* ════════════ Left Hero Showcase Panel ════════════ */}
      <section className={styles.showcaseSide}>
        <div className={styles.showcaseGridPattern} aria-hidden="true" />

        {/* Top Branding Bar */}
        <div className={styles.showcaseBrand}>
          <div className={styles.brandGroup}>
            <div className={styles.showcaseLogoBadge}>
              <img src="/meiyari-mark.png" alt="Meiyari Shield" className={styles.showcaseLogoImg} />
            </div>
            <span className={styles.showcaseBrandName}>MEIYARI</span>
          </div>
          <span className={styles.brandBadgePill}>ENTERPRISE IDENTITY</span>
        </div>

        {/* Center Hero Content */}
        <div className={styles.showcaseHero}>
          <h1 className={styles.showcaseHeading}>
            Trusted Identity <br />
            <span className={styles.highlightText}>Verification &amp; Access</span> <br />
            Intelligence Platform.
          </h1>
          <p className={styles.showcaseSubheading}>
            Meiyari secures every checkpoint with real-time biometric matching and a mandatory two-step
            sign-in — built for officers who can't afford a false clearance.
          </p>

          {/* Feature Highlights */}
          <div className={styles.featureList}>
            <div className={styles.featureItem}>
              <div className={styles.featureIconBox}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </svg>
              </div>
              <div className={styles.featureTextCol}>
                <span className={styles.featureTitle}>Two-Step Sign-In</span>
                <span className={styles.featureDesc}>Every sign-in needs your password and a one-time code — no exceptions, no shortcuts.</span>
              </div>
            </div>

            <div className={styles.featureItem}>
              <div className={styles.featureIconBox}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                  <circle cx="12" cy="13" r="4" />
                </svg>
              </div>
              <div className={styles.featureTextCol}>
                <span className={styles.featureTitle}>Face Verification</span>
                <span className={styles.featureDesc}>Live camera matching against the official document photo.</span>
              </div>
            </div>

            <div className={styles.featureItem}>
              <div className={styles.featureIconBox}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                  <path d="m9 12 2 2 4-4" />
                </svg>
              </div>
              <div className={styles.featureTextCol}>
                <span className={styles.featureTitle}>Full Activity History</span>
                <span className={styles.featureDesc}>Every check performed is recorded, so nothing goes unaccounted for.</span>
              </div>
            </div>
          </div>
        </div>

        {/* Showcase Footer */}
        <div className={styles.showcaseFooter}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" className={styles.trustShieldIcon}>
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
          <span>Trusted for Border &amp; Identity Clearance Nationwide</span>
        </div>
      </section>

      {/* ════════════ Right Form Panel ════════════ */}
      <section className={styles.formSide}>
        <div className={styles.authCard}>
          {/* Card Header */}
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>
              {pendingMfa ? 'Two-Factor Authentication' : 'Sign In'}
            </h2>
            <p className={styles.cardSubtitle}>
              {pendingMfa
                ? `Enter the 6-digit code from your authenticator app for ${pendingMfa.user?.name || pendingMfa.user?.username || 'your account'}.`
                : 'Enter your credentials to access the document verification platform.'}
            </p>
          </div>

          {/* Registration Success Banner */}
          {successNotice && !error && !pendingMfa && (
            <div className={styles.successAlert} role="status">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              <span>{successNotice}</span>
            </div>
          )}

          {/* Error Banner */}
          {error && (
            <div className={styles.errorAlert} role="alert">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <span>{error}</span>
            </div>
          )}

          {/* Step 1: Standard Username/Email & Password Login */}
          {!pendingMfa ? (
            <form className={styles.authForm} onSubmit={handleCredentialSubmit}>
              <div className={styles.formGroup}>
                <label className={styles.inputLabel} htmlFor="identifier">
                  Username or Email Address
                </label>
                <div className={styles.inputWell}>
                  <span className={styles.inputIcon}>
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                      <circle cx="12" cy="7" r="4" />
                    </svg>
                  </span>
                  <input
                    id="identifier"
                    type="text"
                    className={styles.textInput}
                    value={identifier}
                    onChange={(e) => setIdentifier(e.target.value)}
                    placeholder="Enter your username or email address"
                    required
                    autoFocus
                  />
                </div>
              </div>

              <div className={styles.formGroup}>
                <label className={styles.inputLabel} htmlFor="password">
                  Password
                </label>
                <div className={styles.inputWell}>
                  <span className={styles.inputIcon}>
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
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
                    placeholder="Enter your security password"
                    required
                  />
                  <button
                    type="button"
                    className={styles.togglePassBtn}
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                        <line x1="1" y1="1" x2="23" y2="23" />
                      </svg>
                    ) : (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>

              <div className={styles.formOptionsRow}>
                <label className={styles.checkboxLabel}>
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                  />
                  <span>Remember me</span>
                </label>
                <a href="#forgot" onClick={(e) => { e.preventDefault(); alert('Please contact your administrator to reset your credentials.'); }} className={styles.forgotLink}>
                  Forgot Password?
                </a>
              </div>

              <button type="submit" className={styles.submitBtn} disabled={loading}>
                <span>{loading ? 'Authenticating...' : 'Sign In'}</span>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </button>

              <div className={styles.cardFooter}>
                <span>Don't have an account?</span>
                <Link to="/register" className={styles.footerLink}>
                  Create an Account
                </Link>
              </div>
            </form>
          ) : (
            /* Step 2: Standard TOTP MFA Verification */
            <div className={styles.mfaBox}>
              <div className={styles.mfaNotice}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0 }}>
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </svg>
                <span>Open Google Authenticator or your authenticator app and enter the current 6-digit code.</span>
              </div>

              <div className={styles.mfaDigitsRow} onPaste={handleDigitPaste}>
                {mfaDigits.map((digit, idx) => (
                  <input
                    key={idx}
                    ref={(el) => (digitRefs.current[idx] = el)}
                    type="text"
                    inputMode="numeric"
                    maxLength={1}
                    className={styles.digitInput}
                    value={digit}
                    onChange={(e) => handleDigitChange(idx, e.target.value)}
                    onKeyDown={(e) => handleDigitKeyDown(idx, e)}
                    aria-label={`Digit ${idx + 1}`}
                  />
                ))}
              </div>

              <button
                type="button"
                className={styles.submitBtn}
                onClick={handleMfaSubmit}
                disabled={mfaDigits.some((d) => !d)}
              >
                <span>Verify &amp; Sign In</span>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </button>

              <button
                type="button"
                className={styles.backBtn}
                onClick={() => {
                  cancelMfa();
                  setError('');
                }}
              >
                ← Return to Credentials
              </button>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
