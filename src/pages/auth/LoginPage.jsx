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
  const { initiateLogin, verifyMfa, quickDemoLogin, pendingMfa, cancelMfa } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [identifier, setIdentifier] = useState('rajesh.kumar');
  const [password, setPassword] = useState('password123');
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

  async function handleQuickFillMfa() {
    const hint = pendingMfa?.mfaCodeHint || '614920';
    const digits = hint.split('');
    setMfaDigits(digits);
    setError('');
    try {
      await verifyMfa(hint);
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
            Next-Generation <br />
            <span className={styles.highlightText}>Identity &amp; Credential</span> <br />
            Clearance.
          </h1>
          <p className={styles.showcaseSubheading}>
            Comprehensive document verification, facial biometric matching, and mandatory multi-factor security
            protecting every authorized session.
          </p>

          {/* Feature Highlights */}
          <div className={styles.featureList}>
            <div className={styles.featureItem}>
              <div className={styles.featureIconBox}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                  <path d="m9 12 2 2 4-4" />
                </svg>
              </div>
              <div className={styles.featureTextCol}>
                <span className={styles.featureTitle}>Multi-Document Verification</span>
                <span className={styles.featureDesc}>Passports, Driving Licences, Aadhaar, and national identity credentials.</span>
              </div>
            </div>

            <div className={styles.featureItem}>
              <div className={styles.featureIconBox}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </svg>
              </div>
              <div className={styles.featureTextCol}>
                <span className={styles.featureTitle}>Multi-Factor Authentication (TOTP)</span>
                <span className={styles.featureDesc}>Time-based one-time passwords protect against unauthorized account access.</span>
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
                <span className={styles.featureTitle}>Biometric Face Verification</span>
                <span className={styles.featureDesc}>Real-time webcam matching against high-resolution official document portraits.</span>
              </div>
            </div>
          </div>
        </div>

        {/* Showcase Footer */}
        <div className={styles.showcaseFooter}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" className={styles.trustShieldIcon}>
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
          <span>Approved for Enterprise Border &amp; Identity Clearance · ISO 27001 &amp; ICAO Compliant</span>
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
                    placeholder="e.g. rajesh.kumar or email@meiyari.gov"
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

              <div className={styles.dividerRow}>
                <span className={styles.dividerLine} />
                <span className={styles.dividerText}>or quick access</span>
                <span className={styles.dividerLine} />
              </div>

              <button
                type="button"
                className={styles.demoBtn}
                onClick={handleQuickDemo}
                title="Sign in immediately as Demo Officer"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                </svg>
                <span>1-Click Quick Demo Sign-In</span>
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
                className={styles.demoBtn}
                onClick={handleQuickFillMfa}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                </svg>
                <span>Use Demo Code (614920)</span>
              </button>

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
