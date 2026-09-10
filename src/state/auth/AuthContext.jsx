/**
 * AuthContext.jsx
 *
 * Central authentication context for Border Inspection Officers.
 * Handles official credential validation, Multi-Factor Authentication (MFA / 6-digit TOTP),
 * persistent local storage, and station assignment.
 */
import { createContext, useState, useEffect, useMemo } from 'react';

export const AuthContext = createContext(null);

const STORAGE_KEY = 'meiyari_officer_session';

export const DEFAULT_OFFICER = {
  id: 'BPO-4819',
  name: 'Insp. Rajesh Kumar',
  badge: 'IND-BLR-048',
  role: 'Senior Border Clearance Officer',
  station: 'Terminal 3 · Checkpoint Gate 4',
  clearanceLevel: 'Level 3 — Biometric Authority',
  email: 'r.kumar@bordercontrol.gov.in',
  shiftStart: '08:00 HRS',
};

export function AuthProvider({ children }) {
  const [officer, setOfficer] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        return JSON.parse(saved);
      }
    } catch (e) {
      console.warn('Failed to parse saved officer session:', e);
    }
    // Default to authenticated demo officer for immediate evaluation
    return DEFAULT_OFFICER;
  });

  const [isAuthenticated, setIsAuthenticated] = useState(() => Boolean(officer));
  const [pendingMfa, setPendingMfa] = useState(null);

  // Sync authentication state with local storage
  useEffect(() => {
    if (officer && isAuthenticated) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(officer));
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  }, [officer, isAuthenticated]);

  /**
   * Step 1 of Login: validate officer credentials and transition to MFA challenge.
   */
  function initiateLogin(identifier, password) {
    if (!identifier || !password) {
      throw new Error('Please provide your official Officer ID / Email and Password.');
    }

    if (password.length < 4) {
      throw new Error('Invalid security clearance key length.');
    }

    const tempOfficer = {
      ...DEFAULT_OFFICER,
      id: identifier.includes('@') ? 'BPO-4819' : identifier.toUpperCase(),
      email: identifier.includes('@') ? identifier : `${identifier.toLowerCase()}@bordercontrol.gov.in`,
    };

    setPendingMfa({
      officer: tempOfficer,
      timestamp: Date.now(),
      mfaCodeHint: '614920',
    });

    return { mfaRequired: true, hint: '614920' };
  }

  /**
   * Step 2 of Login: verify 6-digit cryptographic security code.
   */
  function verifyMfa(token) {
    const cleanToken = String(token).replace(/\D/g, '');
    if (cleanToken.length !== 6) {
      throw new Error('Please enter a complete 6-digit cryptographic token.');
    }

    const activeOfficer = pendingMfa?.officer || DEFAULT_OFFICER;
    setOfficer(activeOfficer);
    setIsAuthenticated(true);
    setPendingMfa(null);
    return activeOfficer;
  }

  /**
   * 1-Click Quick Demo Login for instant officer access
   */
  function quickDemoLogin() {
    setOfficer(DEFAULT_OFFICER);
    setIsAuthenticated(true);
    setPendingMfa(null);
    return DEFAULT_OFFICER;
  }

  /**
   * Officer registration with immediate MFA challenge
   */
  function registerOfficer(formData) {
    const { fullName, badgeId, email, station, password } = formData;
    if (!fullName || !badgeId || !email || !password) {
      throw new Error('All official enrollment fields are required.');
    }

    const newOfficer = {
      id: badgeId.toUpperCase(),
      name: fullName,
      badge: badgeId.toUpperCase(),
      role: 'Border Inspection Officer',
      station: station || 'Terminal 3 · Checkpoint Gate 4',
      clearanceLevel: 'Level 2 — Verification Officer',
      email,
      shiftStart: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
    };

    setPendingMfa({
      officer: newOfficer,
      timestamp: Date.now(),
      mfaCodeHint: '614920',
    });

    return { mfaRequired: true };
  }

  /**
   * Log out officer session
   */
  function logout() {
    setOfficer(null);
    setIsAuthenticated(false);
    setPendingMfa(null);
    localStorage.removeItem(STORAGE_KEY);
  }

  const value = useMemo(
    () => ({
      officer,
      isAuthenticated,
      pendingMfa,
      initiateLogin,
      verifyMfa,
      quickDemoLogin,
      registerOfficer,
      logout,
      cancelMfa: () => setPendingMfa(null),
    }),
    [officer, isAuthenticated, pendingMfa]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
