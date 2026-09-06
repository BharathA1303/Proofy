/**
 * useVerification.js
 *
 * Custom hook to access the verification context.
 * Separated from VerificationContext.jsx to satisfy React fast-refresh rules —
 * a file should only export components OR hooks/utilities, not both.
 *
 * Usage:
 *   import { useVerification } from '../state/verification/useVerification.js';
 *   const { session, actions } = useVerification();
 */
import { useContext } from 'react';
import { VerificationContext } from './verificationContext.js';

export function useVerification() {
  const ctx = useContext(VerificationContext);
  if (!ctx) {
    throw new Error('useVerification must be used within <VerificationProvider>');
  }
  return ctx;
}
