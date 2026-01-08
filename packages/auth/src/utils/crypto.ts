/**
 * Cryptographic utilities for session token encryption
 *
 * Uses AES-256-GCM for authenticated encryption of session cookies.
 * The encryption key should be stored securely (e.g., in SSM Parameter Store)
 * and injected at build time or read from environment.
 */

import * as crypto from 'crypto';
import type { DashborionSession, EncryptedPayload } from '../types';

// Algorithm configuration
const ALGORITHM = 'aes-256-gcm';
const IV_LENGTH = 16; // 128 bits
const AUTH_TAG_LENGTH = 16; // 128 bits
const KEY_LENGTH = 32; // 256 bits

/**
 * Get encryption key from environment or config
 * In production, this should be loaded from SSM Parameter Store at build time
 */
function getEncryptionKey(): Buffer {
  const keyBase64 = process.env.SESSION_ENCRYPTION_KEY;

  if (!keyBase64) {
    throw new Error('SESSION_ENCRYPTION_KEY not configured');
  }

  const key = Buffer.from(keyBase64, 'base64');

  if (key.length !== KEY_LENGTH) {
    throw new Error(`Invalid encryption key length: expected ${KEY_LENGTH}, got ${key.length}`);
  }

  return key;
}

/**
 * Generate a new random encryption key (for initial setup)
 */
export function generateEncryptionKey(): string {
  const key = crypto.randomBytes(KEY_LENGTH);
  return key.toString('base64');
}

/**
 * Encrypt session data using AES-256-GCM
 */
export function encryptSession(session: DashborionSession): string {
  const key = getEncryptionKey();
  const iv = crypto.randomBytes(IV_LENGTH);

  const cipher = crypto.createCipheriv(ALGORITHM, key, iv, {
    authTagLength: AUTH_TAG_LENGTH,
  });

  const plaintext = JSON.stringify(session);
  const encrypted = Buffer.concat([
    cipher.update(plaintext, 'utf8'),
    cipher.final(),
  ]);

  const authTag = cipher.getAuthTag();

  const payload: EncryptedPayload = {
    data: encrypted.toString('base64'),
    iv: iv.toString('base64'),
    tag: authTag.toString('base64'),
  };

  return Buffer.from(JSON.stringify(payload)).toString('base64');
}

/**
 * Decrypt session data using AES-256-GCM
 * Returns null if decryption fails (invalid token, tampering, etc.)
 */
export function decryptSession(token: string): DashborionSession | null {
  try {
    const key = getEncryptionKey();

    // Decode the outer base64 wrapper
    const payloadJson = Buffer.from(token, 'base64').toString('utf8');
    const payload: EncryptedPayload = JSON.parse(payloadJson);

    const iv = Buffer.from(payload.iv, 'base64');
    const authTag = Buffer.from(payload.tag, 'base64');
    const encrypted = Buffer.from(payload.data, 'base64');

    const decipher = crypto.createDecipheriv(ALGORITHM, key, iv, {
      authTagLength: AUTH_TAG_LENGTH,
    });

    decipher.setAuthTag(authTag);

    const decrypted = Buffer.concat([
      decipher.update(encrypted),
      decipher.final(),
    ]);

    const session: DashborionSession = JSON.parse(decrypted.toString('utf8'));

    return session;
  } catch (error) {
    // Log error for debugging but don't expose details
    console.error('Session decryption failed:', error instanceof Error ? error.message : 'Unknown error');
    return null;
  }
}

/**
 * Validate session is not expired
 */
export function isSessionValid(session: DashborionSession): boolean {
  const now = Math.floor(Date.now() / 1000);
  return session.expiresAt > now;
}

/**
 * Create a session from SAML attributes
 */
export function createSession(
  attributes: {
    userId: string;
    email: string;
    displayName: string;
    groups: string[];
    mfaVerified: boolean;
  },
  ttlSeconds: number,
  ipAddress: string
): DashborionSession {
  const { v4: uuidv4 } = require('uuid');
  const { derivePermissions } = require('../types');

  const now = Math.floor(Date.now() / 1000);
  const permissions = derivePermissions(attributes.groups);

  // Extract roles from permissions
  const roles = [...new Set(permissions.map((p: { role: string }) => p.role))];

  return {
    userId: attributes.userId,
    email: attributes.email,
    displayName: attributes.displayName,
    groups: attributes.groups,
    roles: roles as DashborionSession['roles'],
    permissions,
    sessionId: uuidv4(),
    issuedAt: now,
    expiresAt: now + ttlSeconds,
    mfaVerified: attributes.mfaVerified,
    ipAddress,
  };
}

/**
 * Hash a value (e.g., for session ID comparison)
 */
export function hashValue(value: string): string {
  return crypto.createHash('sha256').update(value).digest('hex');
}
