/**
 * verificationContext.js
 *
 * Exports the raw React context object.
 * Kept in a separate non-component file to satisfy React fast-refresh rules.
 */
import { createContext } from 'react';

export const VerificationContext = createContext(null);
