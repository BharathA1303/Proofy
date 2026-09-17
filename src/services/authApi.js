/**
 * authApi.js
 *
 * Frontend service for the Meiyari officer account authentication API.
 * All credential validation, password hashing, and TOTP secret storage
 * happen server-side — the browser never persists a raw password or secret.
 */
import { API_BASE_URL } from '../config/appConfig.js';

async function postJson(path, body) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Request failed (${res.status})`);
  }
  return data;
}

/** Step 1 of registration: submit account fields, receive TOTP secret + QR URI. */
export function registerStart(formData) {
  return postJson('/api/v1/auth/register/start', formData);
}

/** Step 2 of registration: confirm the 6-digit TOTP code to persist the account. */
export function registerComplete(registrationToken, code) {
  return postJson('/api/v1/auth/register/complete', { registrationToken, code });
}

/** Step 1 of login: verify username/email + password. */
export function login(identifier, password) {
  return postJson('/api/v1/auth/login', { identifier, password });
}

/** Step 2 of login: verify the 6-digit TOTP code, receive the officer session profile. */
export function loginVerifyMfa(loginToken, code) {
  return postJson('/api/v1/auth/login/verify-mfa', { loginToken, code });
}
