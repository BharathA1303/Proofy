/**
 * RegisterPage.jsx
 *
 * Professional User Registration & TOTP MFA Setup Portal.
 * Features:
 *   - Clean standard account creation (Full Name, Username, Email, Password)
 *   - Visual QR Code generation for Google Authenticator / Microsoft Authenticator / Authy
 *   - Base32 Secret Key display with 1-click copy
 *   - 6-digit TOTP activation confirmation
 *   - Persistent account registration into localStorage
 */
import { useState, useRef, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../state/auth/useAuth.js';
import QRCodeView from '../../components/common/QRCodeView.jsx';
import styles from './RegisterPage.module.css';

export default function RegisterPage() {
  const { startRegistration, completeRegistrationMfa, pendingRegistration, cancelRegistration } = useAuth();
  const navigate = useNavigate();

  // Step 1 Form Data
  const [formData, setFormData] = useState({
    fullName: '',
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
  });

  // Step 2 MFA confirmation state
  const [mfaDigits, setMfaDigits] = useState(['', '', '', '', '', '']);
  const [copiedSecret, setCopiedSecret] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const digitRefs = useRef([]);

  // Auto-focus first digit on Step 2
  useEffect(() => {
    if (pendingRegistration) {
      setTimeout(() => digitRefs.current[0]?.focus(), 100);
    }
  }, [pendingRegistration]);

  function handleChange(field, val) {
    setFormData((prev) => ({ ...prev, [field]: val }));
  }

  function handleStep1Submit(e) {
    e.preventDefault();
    setError('');

    if (formData.password !== formData.confirmPassword) {
      setError('Passwords do not match. Please verify and re-enter.');
      return;
    }

    if (formData.password.length < 6) {
      setError('Password must be at least 6 characters in length.');
      return;
    }

    setLoading(true);
    try {
      startRegistration({
        fullName: formData.fullName,
        username: formData.username,
        email: formData.email,
        password: formData.password,
      });
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

  function handleStep2Submit(e) {
    e?.preventDefault();
    setError('');
    const code = mfaDigits.join('');

    try {
      completeRegistrationMfa(code);
      // Navigate to login with success confirmation
      navigate('/login', {
        state: {
          registeredMessage: `Account successfully created for ${formData.username || 'your user'}! Please sign in with your credentials.`,
        },
      });
    } catch (err) {
      setError(err.message);
    }
  }

  function handleQuickFillMfa() {
    const hint = pendingRegistration?.hint || '614920';
    setMfaDigits(hint.split(''));
    setError('');
    try {
      completeRegistrationMfa(hint);
      navigate('/login', {
        state: {
          registeredMessage: `Account successfully created! Please sign in with your username and password.`,
        },
      });
    } catch (err) {
      setError(err.message);
    }
  }

  function handleCopySecret() {
    const secret = pendingRegistration?.secret || 'JBSWY3DPEHPK3PXP';
    navigator.clipboard.writeText(secret);
    setCopiedSecret(true);
    setTimeout(() => setCopiedSecret(false), 2000);
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
          <span className={styles.brandBadgePill}>ACCOUNT REGISTRATION</span>
        </div>

        {/* Center Hero Content */}
        <div className={styles.showcaseHero}>
          <h1 className={styles.showcaseHeading}>
            Register for <br />
            <span className={styles.highlightText}>Secure Verification</span> <br />
            Terminal Access.
          </h1>
          <p className={styles.showcaseSubheading}>
            Join the Meiyari identity clearance infrastructure. Every account is protected with enterprise
            multi-factor authenticator pairing.
          </p>

          {/* Simple 2-Step Workflow Explanation */}
          <div className={styles.stepsList}>
            <div className={styles.stepItem}>
              <div className={styles.stepNumber}>1</div>
              <div className={styles.stepTextCol}>
                <span className={styles.stepTitle}>Account Profile Credentials</span>
                <span className={styles.stepDesc}>Register your official name, username, email, and secure password.</span>
              </div>
            </div>

            <div className={styles.stepItem}>
              <div className={styles.stepNumber}>2</div>
              <div className={styles.stepTextCol}>
                <span className={styles.stepTitle}>Authenticator App Pairing (MFA)</span>
                <span className={styles.stepDesc}>Scan the high-security QR code with Google Authenticator or Microsoft Authenticator.</span>
              </div>
            </div>
          </div>
        </div>

        {/* Showcase Footer */}
        <div className={styles.showcaseFooter}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" className={styles.trustShieldIcon}>
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
          <span>Time-Based One-Time Password (TOTP) Standard · RFC 6238 Compliant</span>
        </div>
      </section>

      {/* ════════════ Right Form Panel ════════════ */}
      <section className={styles.formSide}>
        <div className={styles.authCard}>
          {/* Step Progress Pills */}
          <div className={styles.stepTrackerRow}>
            <div className={`${styles.stepPill} ${!pendingRegistration ? styles.stepPillActive : styles.stepPillDone}`}>
              <span>1. Credentials</span>
            </div>
            <div className={styles.stepConnector} />
            <div className={`${styles.stepPill} ${pendingRegistration ? styles.stepPillActive : ''}`}>
              <span>2. MFA Setup</span>
            </div>
          </div>

          {/* Card Header */}
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>
              {!pendingRegistration ? 'Create Account' : 'Set Up Authenticator'}
            </h2>
            <p className={styles.cardSubtitle}>
              {!pendingRegistration
                ? 'Enter your details to register for the verification platform.'
                : 'Scan the QR code below using your authenticator app to complete setup.'}
            </p>
          </div>

          {/* Error Banner */}
          {error && (
            <div className={styles.errorAlert} role="alert">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
              </svg>
              <span>{error}</span>
            </div>
          )}

          {/* ── STEP 1: Account Details Form ── */}
          {!pendingRegistration ? (
            <form className={styles.authForm} onSubmit={handleStep1Submit}>
              <div className={styles.formGroup}>
                <label className={styles.inputLabel} htmlFor="regFullName">Full Name</label>
                <div className={styles.inputWell}>
                  <input
                    id="regFullName"
                    type="text"
                    className={styles.textInput}
                    placeholder="e.g. Vikram Singh"
                    value={formData.fullName}
                    onChange={(e) => handleChange('fullName', e.target.value)}
                    required
                    autoFocus
                  />
                </div>
              </div>

              <div className={styles.fieldRow}>
                <div className={styles.formGroup}>
                  <label className={styles.inputLabel} htmlFor="regUsername">Username</label>
                  <div className={styles.inputWell}>
                    <input
                      id="regUsername"
                      type="text"
                      className={styles.textInput}
                      placeholder="e.g. vikram.singh"
                      value={formData.username}
                      onChange={(e) => handleChange('username', e.target.value)}
                      required
                    />
                  </div>
                </div>

                <div className={styles.formGroup}>
                  <label className={styles.inputLabel} htmlFor="regEmail">Email Address</label>
                  <div className={styles.inputWell}>
                    <input
                      id="regEmail"
                      type="email"
                      className={styles.textInput}
                      placeholder="vikram@example.com"
                      value={formData.email}
                      onChange={(e) => handleChange('email', e.target.value)}
                      required
                    />
                  </div>
                </div>
              </div>

              <div className={styles.fieldRow}>
                <div className={styles.formGroup}>
                  <label className={styles.inputLabel} htmlFor="regPassword">Password</label>
                  <div className={styles.inputWell}>
                    <input
                      id="regPassword"
                      type="password"
                      className={styles.textInput}
                      placeholder="Min. 6 characters"
                      value={formData.password}
                      onChange={(e) => handleChange('password', e.target.value)}
                      required
                    />
                  </div>
                </div>

                <div className={styles.formGroup}>
                  <label className={styles.inputLabel} htmlFor="regConfirm">Confirm Password</label>
                  <div className={styles.inputWell}>
                    <input
                      id="regConfirm"
                      type="password"
                      className={styles.textInput}
                      placeholder="Re-enter password"
                      value={formData.confirmPassword}
                      onChange={(e) => handleChange('confirmPassword', e.target.value)}
                      required
                    />
                  </div>
                </div>
              </div>

              <button type="submit" className={styles.submitBtn} disabled={loading}>
                <span>{loading ? 'Preparing MFA...' : 'Continue to Two-Factor Setup'}</span>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </button>

              <div className={styles.cardFooter}>
                <span>Already have an account?</span>
                <Link to="/login" className={styles.footerLink}>
                  Sign In
                </Link>
              </div>
            </form>
          ) : (
            /* ── STEP 2: MFA TOTP Setup with QR Code & Key ── */
            <div className={styles.qrSetupSection}>
              {/* Visual QR Code */}
              <div className={styles.qrWrapper}>
                <QRCodeView
                  value={pendingRegistration.qrUri}
                  size={160}
                />
              </div>

              {/* Secret Key Display Box */}
              <div className={styles.secretKeyBox}>
                <div className={styles.secretKeyHeader}>
                  <span>MANUAL SETUP SECRET KEY</span>
                  <span>BASE32</span>
                </div>
                <div className={styles.secretKeyDisplayRow}>
                  <span className={styles.secretKeyText}>{pendingRegistration.secret || 'JBSWY3DPEHPK3PXP'}</span>
                  <button
                    type="button"
                    className={styles.copyKeyBtn}
                    onClick={handleCopySecret}
                    title="Copy secret key to clipboard"
                  >
                    {copiedSecret ? '✓ Copied' : 'Copy Key'}
                  </button>
                </div>
              </div>

              {/* 6-Digit TOTP Verification Input */}
              <span className={styles.mfaPromptLabel}>
                Enter the 6-digit code displayed in your authenticator app:
              </span>

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
                onClick={handleStep2Submit}
                disabled={mfaDigits.some((d) => !d)}
              >
                <span>Activate MFA &amp; Complete Registration</span>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </button>

              <button
                type="button"
                className={styles.backBtn}
                onClick={() => {
                  cancelRegistration();
                  setError('');
                }}
              >
                ← Back to Edit Details
              </button>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
