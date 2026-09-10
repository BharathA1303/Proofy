/**
 * appConfig.js
 *
 * Central application configuration.
 * Change APP_NAME here — it propagates everywhere via import.
 * Do NOT scatter the product name as literals throughout components.
 */

export const APP_NAME = 'Meiyari';
export const APP_SHORT_NAME = 'Meiyari';
export const APP_TAGLINE = 'AI-Powered Identity & Document Verification';
export const APP_VERSION = '2.0';
export const ENVIRONMENT = 'production';

/**
 * API base URL — replace with real FastAPI endpoint in Phase 1.
 * Read from env var first; fall back to localhost for local development.
 */
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

/**
 * Feature flags
 */
export const FEATURES = {
  /** Enable real backend verification calls */
  BACKEND_ENABLED: true,
  /** Enable sample document loading */
  SAMPLE_DOCUMENTS: true,
  /** Enable forensic evidence panel */
  FORENSIC_PANEL: true,
  /** Enable blockchain audit integrity verification */
  BLOCKCHAIN_AUDIT: true,
};

