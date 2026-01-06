/**
 * Session management utilities for Lambda@Edge
 *
 * Handles cookie parsing, creation, and session validation.
 */

import type {
  CloudFrontHeaders,
  CloudFrontRequest,
  DashborionSession,
  AuthHeaders,
} from '../types';
import { decryptSession, isSessionValid } from './crypto';

// Default cookie name
const DEFAULT_COOKIE_NAME = 'dashborion_session';

/**
 * Parse cookies from CloudFront request headers
 */
export function parseCookies(headers: CloudFrontHeaders): Record<string, string> {
  const cookies: Record<string, string> = {};

  const cookieHeader = headers.cookie;
  if (!cookieHeader || cookieHeader.length === 0) {
    return cookies;
  }

  const cookieString = cookieHeader[0].value;
  const pairs = cookieString.split(';');

  for (const pair of pairs) {
    const [name, ...valueParts] = pair.trim().split('=');
    if (name) {
      cookies[name] = valueParts.join('=');
    }
  }

  return cookies;
}

/**
 * Get session from request cookies
 * Returns null if no session or invalid session
 */
export function getSessionFromRequest(
  request: CloudFrontRequest,
  cookieName: string = DEFAULT_COOKIE_NAME
): DashborionSession | null {
  const cookies = parseCookies(request.headers);
  const sessionToken = cookies[cookieName];

  if (!sessionToken) {
    return null;
  }

  const session = decryptSession(sessionToken);

  if (!session) {
    return null;
  }

  if (!isSessionValid(session)) {
    return null;
  }

  return session;
}

/**
 * Create Set-Cookie header value
 */
export function createCookieHeader(
  name: string,
  value: string,
  options: {
    domain?: string;
    path?: string;
    expires?: Date;
    maxAge?: number;
    secure?: boolean;
    httpOnly?: boolean;
    sameSite?: 'Strict' | 'Lax' | 'None';
  } = {}
): string {
  const parts = [`${name}=${value}`];

  if (options.domain) {
    parts.push(`Domain=${options.domain}`);
  }

  parts.push(`Path=${options.path || '/'}`);

  if (options.expires) {
    parts.push(`Expires=${options.expires.toUTCString()}`);
  }

  if (options.maxAge !== undefined) {
    parts.push(`Max-Age=${options.maxAge}`);
  }

  if (options.secure !== false) {
    parts.push('Secure');
  }

  if (options.httpOnly !== false) {
    parts.push('HttpOnly');
  }

  parts.push(`SameSite=${options.sameSite || 'Lax'}`);

  return parts.join('; ');
}

/**
 * Create session cookie
 */
export function createSessionCookie(
  token: string,
  expiresAt: number,
  domain?: string,
  cookieName: string = DEFAULT_COOKIE_NAME
): string {
  return createCookieHeader(cookieName, token, {
    domain,
    path: '/',
    expires: new Date(expiresAt * 1000),
    secure: true,
    httpOnly: true,
    sameSite: 'Lax',
  });
}

/**
 * Create cookie to clear session (logout)
 */
export function createLogoutCookie(
  domain?: string,
  cookieName: string = DEFAULT_COOKIE_NAME
): string {
  return createCookieHeader(cookieName, '', {
    domain,
    path: '/',
    expires: new Date(0), // Epoch = delete cookie
    secure: true,
    httpOnly: true,
    sameSite: 'Lax',
  });
}

/**
 * Add auth headers to request for forwarding to API
 */
export function addAuthHeaders(
  request: CloudFrontRequest,
  session: DashborionSession
): void {
  const headers = request.headers;

  // User identity
  headers['x-auth-user-id'] = [{ key: 'X-Auth-User-Id', value: session.userId }];
  headers['x-auth-user-email'] = [{ key: 'X-Auth-User-Email', value: session.email }];

  // Groups and roles
  headers['x-auth-user-groups'] = [{ key: 'X-Auth-User-Groups', value: session.groups.join(',') }];
  headers['x-auth-user-roles'] = [{ key: 'X-Auth-User-Roles', value: session.roles.join(',') }];

  // Session metadata
  headers['x-auth-session-id'] = [{ key: 'X-Auth-Session-Id', value: session.sessionId }];
  headers['x-auth-mfa-verified'] = [{ key: 'X-Auth-MFA-Verified', value: String(session.mfaVerified) }];

  // Permissions (JSON encoded for complex data)
  headers['x-auth-permissions'] = [
    { key: 'X-Auth-Permissions', value: Buffer.from(JSON.stringify(session.permissions)).toString('base64') },
  ];
}

/**
 * Get client IP from CloudFront request
 */
export function getClientIp(request: CloudFrontRequest): string {
  const xForwardedFor = request.headers['x-forwarded-for'];
  if (xForwardedFor && xForwardedFor.length > 0) {
    // X-Forwarded-For can contain multiple IPs, first is the client
    return xForwardedFor[0].value.split(',')[0].trim();
  }

  const cloudFrontViewerAddress = request.headers['cloudfront-viewer-address'];
  if (cloudFrontViewerAddress && cloudFrontViewerAddress.length > 0) {
    // CloudFront-Viewer-Address contains IP:port
    return cloudFrontViewerAddress[0].value.split(':')[0];
  }

  return 'unknown';
}

/**
 * Get host from request
 */
export function getHost(request: CloudFrontRequest): string {
  const hostHeader = request.headers.host;
  if (hostHeader && hostHeader.length > 0) {
    return hostHeader[0].value;
  }
  return '';
}

/**
 * Build full URL from request
 */
export function getFullUrl(request: CloudFrontRequest): string {
  const host = getHost(request);
  const path = request.uri;
  const querystring = request.querystring ? `?${request.querystring}` : '';
  return `https://${host}${path}${querystring}`;
}

/**
 * Extract relay state (original URL) from querystring
 */
export function getRelayState(request: CloudFrontRequest): string | null {
  if (!request.querystring) {
    return null;
  }

  const params = new URLSearchParams(request.querystring);
  return params.get('RelayState');
}
