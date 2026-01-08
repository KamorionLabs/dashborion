/**
 * Protect Handler - Lambda@Edge viewer-request
 *
 * Validates session cookies and redirects to IdP if not authenticated.
 * Adds auth headers to authenticated requests for API forwarding.
 */

import type {
  CloudFrontRequestEvent,
  CloudFrontRequest,
  CloudFrontResponse,
} from '../types';
import {
  getSessionFromRequest,
  addAuthHeaders,
  getFullUrl,
  getHost,
  createLogoutCookie,
} from '../utils/session';
import { initializeSaml, createLoginRedirectUrl } from '../utils/saml';

// Configuration (injected at build time or from environment)
interface ProtectConfig {
  cookieName: string;
  cookieDomain: string;
  cloudfrontDomain: string;
  idpMetadataXml: string;
  spEntityId: string;
  signAuthnRequests: boolean;
  excludedPaths: string[];
}

// Load config from environment (set during build/deploy)
function getConfig(): ProtectConfig {
  return {
    cookieName: process.env.COOKIE_NAME || 'dashborion_session',
    cookieDomain: process.env.COOKIE_DOMAIN || '',
    cloudfrontDomain: process.env.CLOUDFRONT_DOMAIN || '',
    idpMetadataXml: process.env.IDP_METADATA_XML || '',
    spEntityId: process.env.SP_ENTITY_ID || 'dashborion',
    signAuthnRequests: process.env.SIGN_AUTHN_REQUESTS === 'true',
    excludedPaths: (process.env.EXCLUDED_PATHS || '/saml/acs,/saml/metadata.xml,/health').split(','),
  };
}

/**
 * Check if path should bypass authentication
 */
function isExcludedPath(uri: string, excludedPaths: string[]): boolean {
  return excludedPaths.some((path) => uri.startsWith(path));
}

/**
 * Create redirect response to IdP
 */
function createRedirectToIdp(
  config: ProtectConfig,
  relayState: string
): CloudFrontResponse {
  const { idp, sp } = initializeSaml(config.idpMetadataXml, {
    entityId: config.spEntityId,
    acsUrl: `https://${config.cloudfrontDomain}/saml/acs`,
    signAuthnRequests: config.signAuthnRequests,
  });

  const loginUrl = createLoginRedirectUrl(sp, idp, relayState);

  return {
    status: '302',
    statusDescription: 'Found',
    headers: {
      location: [{ key: 'Location', value: loginUrl }],
      'cache-control': [{ key: 'Cache-Control', value: 'no-cache, no-store, must-revalidate' }],
    },
  };
}

/**
 * Create logout response (clear cookie and redirect to home)
 */
function createLogoutResponse(config: ProtectConfig): CloudFrontResponse {
  return {
    status: '302',
    statusDescription: 'Found',
    headers: {
      location: [{ key: 'Location', value: '/' }],
      'set-cookie': [{ key: 'Set-Cookie', value: createLogoutCookie(config.cookieDomain, config.cookieName) }],
      'cache-control': [{ key: 'Cache-Control', value: 'no-cache, no-store, must-revalidate' }],
    },
  };
}

/**
 * Create unauthorized response
 */
function createUnauthorizedResponse(message: string): CloudFrontResponse {
  return {
    status: '401',
    statusDescription: 'Unauthorized',
    headers: {
      'content-type': [{ key: 'Content-Type', value: 'application/json' }],
      'cache-control': [{ key: 'Cache-Control', value: 'no-cache, no-store, must-revalidate' }],
    },
    body: JSON.stringify({ error: 'Unauthorized', message }),
  };
}

/**
 * Main handler
 */
export async function handler(
  event: CloudFrontRequestEvent
): Promise<CloudFrontRequest | CloudFrontResponse> {
  const request = event.Records[0].cf.request;
  const config = getConfig();

  // Skip auth for excluded paths (SAML endpoints, health checks)
  if (isExcludedPath(request.uri, config.excludedPaths)) {
    return request;
  }

  // Handle logout
  if (request.uri === '/saml/logout' || request.uri === '/logout') {
    return createLogoutResponse(config);
  }

  // Check for valid session
  const session = getSessionFromRequest(request, config.cookieName);

  if (!session) {
    // No valid session - redirect to IdP
    const fullUrl = getFullUrl(request);
    return createRedirectToIdp(config, fullUrl);
  }

  // Valid session - add auth headers and continue
  addAuthHeaders(request, session);

  return request;
}
