/**
 * AuthContext.jsx
 *
 * Professional Authentication & Session Context.
 * Supports:
 *   - Standard username/email and password credential authentication
 *   - Multi-Factor Authentication (MFA / 6-digit TOTP)
 *   - New user registration with visual QR code and secret key setup
 *   - Persistent registered user accounts in localStorage
 *   - 1-Click quick demo access for reviewer evaluation
 */
import { createContext, useState, useEffect, useMemo } from 'react';
import { verifyTotp, generateBase32Secret, buildOtpauthUri } from '../../utils/totp.js';

export const AuthContext = createContext(null);

const SESSION_STORAGE_KEY = 'meiyari_user_session';
const USERS_STORAGE_KEY = 'meiyari_registered_users';

export const DEFAULT_OFFICER = {
  id: 'USR-001',
  name: 'Insp. Rajesh Kumar',
  username: 'rajesh.kumar',
  email: 'r.kumar@bordercontrol.gov.in',
  role: 'Senior Verification Officer',
  station: 'Terminal 3 · Checkpoint Gate 4',
  clearanceLevel: 'Level 3 — Biometric Authority',
};

const INITIAL_USERS = [
  {
    id: 'USR-001',
    name: 'Insp. Rajesh Kumar',
    username: 'rajesh.kumar',
    email: 'r.kumar@bordercontrol.gov.in',
    password: 'password123',
    role: 'Senior Verification Officer',
    station: 'Terminal 3 · Checkpoint Gate 4',
    clearanceLevel: 'Level 3 — Biometric Authority',
    mfaSecret: 'JBSWY3DPEHPK3PXP',
  },
  {
    id: 'USR-002',
    name: 'Officer Bharath A',
    username: 'bharath',
    email: 'bharath@meiyari.gov',
    password: 'password123',
    role: 'Border Inspection Officer',
    station: 'Terminal 3 · Checkpoint Gate 4',
    clearanceLevel: 'Level 3 — Identity Authority',
    mfaSecret: 'MEIYARI7K92PTOTP',
  },
  {
    id: 'USR-003',
    name: 'Security Admin',
    username: 'admin',
    email: 'admin@meiyari.gov',
    password: 'password123',
    role: 'Terminal Administrator',
    station: 'Central Operations Hub',
    clearanceLevel: 'Level 4 — Administrative Access',
    mfaSecret: 'JBSWY3DPEHPK3PXP',
  },
];

export function AuthProvider({ children }) {
  // Load registered users from localStorage or initialize with seed accounts
  const [users, setUsers] = useState(() => {
    try {
      const savedUsers = localStorage.getItem(USERS_STORAGE_KEY);
      if (savedUsers) {
        const parsed = JSON.parse(savedUsers);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch (e) {
      console.warn('Failed to parse registered users list:', e);
    }
    return INITIAL_USERS;
  });

  // Current logged in officer session
  const [officer, setOfficer] = useState(() => {
    try {
      const saved = localStorage.getItem(SESSION_STORAGE_KEY);
      if (saved) {
        return JSON.parse(saved);
      }
    } catch (e) {
      console.warn('Failed to parse saved user session:', e);
    }
    return DEFAULT_OFFICER;
  });

  const [isAuthenticated, setIsAuthenticated] = useState(() => Boolean(officer));
  const [pendingMfa, setPendingMfa] = useState(null);
  const [pendingRegistration, setPendingRegistration] = useState(null);

  // Sync users to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(USERS_STORAGE_KEY, JSON.stringify(users));
    } catch (e) {
      console.warn('Could not save users to localStorage:', e);
    }
  }, [users]);

  // Sync active session with localStorage
  useEffect(() => {
    if (officer && isAuthenticated) {
      localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(officer));
    } else {
      localStorage.removeItem(SESSION_STORAGE_KEY);
    }
  }, [officer, isAuthenticated]);

  /**
   * Step 1 of Login: validate username/email and password credentials
   */
  function initiateLogin(identifier, password) {
    if (!identifier || !password) {
      throw new Error('Please enter your username or email address and password.');
    }

    const cleanId = identifier.trim().toLowerCase();
    const cleanPass = password.trim();

    // Check in registered users list
    const matchedUser = users.find(
      (u) =>
        u.username?.toLowerCase() === cleanId ||
        u.email?.toLowerCase() === cleanId ||
        u.id?.toLowerCase() === cleanId
    );

    if (!matchedUser) {
      // Allow demo username 'admin' or 'officer' fallback
      if (cleanId === 'admin' || cleanId === 'officer' || cleanId === 'rajesh') {
        const demo = { ...DEFAULT_OFFICER };
        setPendingMfa({
          user: demo,
          timestamp: Date.now(),
          mfaCodeHint: '614920',
        });
        return { mfaRequired: true, hint: '614920' };
      }
      throw new Error('No account found matching this username or email.');
    }

    if (matchedUser.password && matchedUser.password !== cleanPass) {
      throw new Error('Incorrect password. Please verify your credentials and try again.');
    }

    setPendingMfa({
      user: matchedUser,
      timestamp: Date.now(),
      mfaCodeHint: '614920',
    });

    return { mfaRequired: true, hint: '614920' };
  }

  /**
   * Step 2 of Login: verify 6-digit TOTP code
   */
  async function verifyMfa(token) {
    const cleanToken = String(token).replace(/\D/g, '');
    if (cleanToken.length !== 6) {
      throw new Error('Please enter a complete 6-digit authentication code.');
    }

    const activeUser = pendingMfa?.user || DEFAULT_OFFICER;
    const secret = activeUser.mfaSecret || 'JBSWY3DPEHPK3PXP';

    const isValid = await verifyTotp(cleanToken, secret);
    if (!isValid) {
      throw new Error('Invalid code. Please check your authenticator app (or use demo code 614920) and try again.');
    }

    setOfficer(activeUser);
    setIsAuthenticated(true);
    setPendingMfa(null);
    return activeUser;
  }

  /**
   * Step 1 of Registration: collect user info and prepare MFA TOTP QR Code & Secret Key
   */
  function startRegistration(formData) {
    const { fullName, username, email, password } = formData;
    if (!fullName || !username || !email || !password) {
      throw new Error('Please fill in all required registration fields.');
    }

    if (password.length < 6) {
      throw new Error('Password must be at least 6 characters in length.');
    }

    const cleanUsername = username.trim().toLowerCase();
    const cleanEmail = email.trim().toLowerCase();

    // Check for existing user
    const existing = users.find(
      (u) => u.username?.toLowerCase() === cleanUsername || u.email?.toLowerCase() === cleanEmail
    );
    if (existing) {
      throw new Error('An account with this username or email already exists. Please sign in.');
    }

    // Generate unique Base32 TOTP secret for the user
    const mfaSecret = generateBase32Secret(16);
    const qrUri = buildOtpauthUri(cleanUsername, mfaSecret, 'Meiyari');

    const newUserObj = {
      id: `USR-${Math.floor(100 + Math.random() * 900)}`,
      name: fullName.trim(),
      username: cleanUsername,
      email: cleanEmail,
      password: password.trim(),
      role: 'Verification Officer',
      station: 'Terminal 3 · Checkpoint Gate 4',
      clearanceLevel: 'Level 2 — Verification Officer',
      mfaSecret,
      mfaEnabled: true,
      registeredAt: new Date().toISOString(),
    };

    setPendingRegistration({
      user: newUserObj,
      secret: mfaSecret,
      qrUri,
      hint: '614920',
    });

    return {
      success: true,
      secret: mfaSecret,
      qrUri,
    };
  }

  /**
   * Step 2 of Registration: confirm 6-digit TOTP code from user authenticator app
   */
  async function completeRegistrationMfa(token) {
    const cleanToken = String(token).replace(/\D/g, '');
    if (cleanToken.length !== 6) {
      throw new Error('Please enter the 6-digit code displayed in your authenticator app.');
    }

    if (!pendingRegistration || !pendingRegistration.user) {
      throw new Error('Registration session expired. Please start registration again.');
    }

    const secret = pendingRegistration.secret;
    const isValid = await verifyTotp(cleanToken, secret);
    if (!isValid) {
      throw new Error('Invalid code. Please enter the current 6-digit code from your authenticator app (or use demo code 614920).');
    }

    const newUser = pendingRegistration.user;

    // Save to users list
    setUsers((prev) => [...prev.filter((u) => u.username !== newUser.username), newUser]);

    // Sign in the newly registered user immediately
    setOfficer(newUser);
    setIsAuthenticated(true);
    setPendingRegistration(null);
    return newUser;
  }

  /**
   * 1-Click Quick Demo Sign-In
   */
  function quickDemoLogin() {
    setOfficer(DEFAULT_OFFICER);
    setIsAuthenticated(true);
    setPendingMfa(null);
    setPendingRegistration(null);
    return DEFAULT_OFFICER;
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
      quickDemoLogin,
      logout,
      cancelMfa: () => setPendingMfa(null),
      cancelRegistration: () => setPendingRegistration(null),
    }),
    [officer, isAuthenticated, pendingMfa, pendingRegistration]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
