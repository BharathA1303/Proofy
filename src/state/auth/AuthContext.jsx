/**
 * AuthContext.jsx
 *
 * Professional Authentication & Session Context.
 * Supports:
 *   - Standard username/email and password credential authentication
 *   - Multi-Factor Authentication (MFA / 6-digit TOTP)
 *   - New user registration with visual QR code and secret key setup
 *
 * Credential validation, password hashing, and TOTP secret storage all
 * happen server-side (see backend/app/api/v1/auth.py) in an encrypted
 * database table. Only the resulting officer session profile — never a
 * password or MFA secret — is cached in localStorage for UI convenience.
 */
import { createContext, useState, useEffect, useMemo } from 'react';
import * as authApi from '../../services/authApi.js';

export const AuthContext = createContext(null);

const SESSION_STORAGE_KEY = 'meiyari_user_session';

// Legacy pre-migration key that stored the full account list — including
// plaintext passwords and MFA secrets — directly in localStorage. Accounts
// now live server-side in an encrypted database table; this key is purged
// on load so it never lingers in a browser that ran the old client-only code.
const LEGACY_USERS_STORAGE_KEY = 'meiyari_registered_users';
try {
  localStorage.removeItem(LEGACY_USERS_STORAGE_KEY);
} catch {
  // localStorage unavailable (e.g. private browsing) — nothing to clean up.
}

export function AuthProvider({ children }) {
  // Current logged in officer session
  // Must default to `null` when there is no saved session — otherwise a fresh
  // browser session would be treated as already authenticated, bypassing login.
  const [officer, setOfficer] = useState(() => {
    try {
      const saved = localStorage.getItem(SESSION_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        // A session written by a pre-migration client-only build may still carry
        // a raw password / MFA secret. Never trust or keep such a session — force
        // the browser back to a clean sign-in through the real backend instead.
        if (parsed && ('password' in parsed || 'mfaSecret' in parsed)) {
          localStorage.removeItem(SESSION_STORAGE_KEY);
          return null;
        }
        return parsed;
      }
    } catch (e) {
      console.warn('Failed to parse saved user session:', e);
    }
    return null;
  });

  const [isAuthenticated, setIsAuthenticated] = useState(() => Boolean(officer));
  const [pendingMfa, setPendingMfa] = useState(null);
  const [pendingRegistration, setPendingRegistration] = useState(null);

  // Sync active session with localStorage
  useEffect(() => {
    if (officer && isAuthenticated) {
      localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(officer));
    } else {
      localStorage.removeItem(SESSION_STORAGE_KEY);
    }
  }, [officer, isAuthenticated]);

  /**
   * Step 1 of Login: validate username/email and password credentials against the backend.
   */
  async function initiateLogin(identifier, password) {
    if (!identifier || !password) {
      throw new Error('Please enter your username or email address and password.');
    }

    const { loginToken } = await authApi.login(identifier.trim(), password.trim());

    setPendingMfa({
      loginToken,
      identifier: identifier.trim(),
      timestamp: Date.now(),
    });

    return { mfaRequired: true };
  }

  /**
   * Step 2 of Login: verify 6-digit TOTP code against the backend.
   */
  async function verifyMfa(token) {
    const cleanToken = String(token).replace(/\D/g, '');
    if (cleanToken.length !== 6) {
      throw new Error('Please enter a complete 6-digit authentication code.');
    }

    if (!pendingMfa?.loginToken) {
      throw new Error('Your session has expired. Please sign in again.');
    }

    const activeOfficer = await authApi.loginVerifyMfa(pendingMfa.loginToken, cleanToken);

    setOfficer(activeOfficer);
    setIsAuthenticated(true);
    setPendingMfa(null);
    return activeOfficer;
  }

  /**
   * Step 1 of Registration: submit account fields, receive MFA TOTP QR Code & Secret Key.
   * The account is NOT yet persisted — only created after MFA confirmation.
   */
  async function startRegistration(formData) {
    const { fullName, username, email, password } = formData;
    if (!fullName || !username || !email || !password) {
      throw new Error('Please fill in all required registration fields.');
    }

    if (password.length < 6) {
      throw new Error('Password must be at least 6 characters in length.');
    }

    const { registrationToken, secret, qrUri } = await authApi.registerStart({
      fullName: fullName.trim(),
      username: username.trim(),
      email: email.trim(),
      password,
    });

    setPendingRegistration({
      registrationToken,
      secret,
      qrUri,
    });

    return { success: true, secret, qrUri };
  }

  /**
   * Step 2 of Registration: confirm 6-digit TOTP code, persisting the encrypted account server-side.
   */
  async function completeRegistrationMfa(token) {
    const cleanToken = String(token).replace(/\D/g, '');
    if (cleanToken.length !== 6) {
      throw new Error('Please enter the 6-digit code displayed in your authenticator app.');
    }

    if (!pendingRegistration?.registrationToken) {
      throw new Error('Registration session expired. Please start registration again.');
    }

    const newOfficer = await authApi.registerComplete(pendingRegistration.registrationToken, cleanToken);

    // Sign in the newly registered user immediately
    setOfficer(newOfficer);
    setIsAuthenticated(true);
    setPendingRegistration(null);
    return newOfficer;
  }

  /**
   * Sign out current session
   */
  function logout() {
    setOfficer(null);
    setIsAuthenticated(false);
    setPendingMfa(null);
    setPendingRegistration(null);
    localStorage.removeItem(SESSION_STORAGE_KEY);
  }

  const value = useMemo(
    () => ({
      officer,
      isAuthenticated,
      pendingMfa,
      pendingRegistration,
      initiateLogin,
      verifyMfa,
      startRegistration,
      completeRegistrationMfa,
      logout,
      cancelMfa: () => setPendingMfa(null),
      cancelRegistration: () => setPendingRegistration(null),
    }),
    [officer, isAuthenticated, pendingMfa, pendingRegistration]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
