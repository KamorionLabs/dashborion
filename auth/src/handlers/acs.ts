/**
 * ACS Handler - SAML Assertion Consumer Service
 *
 * Processes SAML assertions from the IdP, creates session cookies,
 * and redirects users to the original URL.
 */

import type {
  CloudFrontRequestEvent,
  CloudFrontRequest,
  CloudFrontResponse,
} from '../types';
import {
  initializeSaml,
  parseSamlResponse,
  decodeSamlResponse,
  getRelayStateFromBody,
} from '../utils/saml';
import { createSession, encryptSession } from '../utils/crypto';
import { createSessionCookie, getClientIp } from '../utils/session';

// Configuration
interface AcsConfig {
  cookieName: string;
  cookieDomain: string;
  sessionTtlSeconds: number;
  idpMetadataXml: string;
  spEntityId: string;
  signAuthnRequests: boolean;
  defaultRedirectUrl: string;
}

// Load config from environment
function getConfig(): AcsConfig {
  return {
    cookieName: process.env.COOKIE_NAME || 'dashborion_session',
    cookieDomain: process.env.COOKIE_DOMAIN || '',
    sessionTtlSeconds: parseInt(process.env.SESSION_TTL_SECONDS || '3600', 10),
    idpMetadataXml: process.env.IDP_METADATA_XML || '',
    spEntityId: process.env.SP_ENTITY_ID || 'dashborion',
    signAuthnRequests: process.env.SIGN_AUTHN_REQUESTS === 'true',
    defaultRedirectUrl: process.env.DEFAULT_REDIRECT_URL || '/',
  };
}

/**
 * Create error response
 */
function createErrorResponse(status: string, message: string): CloudFrontResponse {
  return {
    status,
    statusDescription: status === '400' ? 'Bad Request' : 'Internal Server Error',
    headers: {
      'content-type': [{ key: 'Content-Type', value: 'text/html; charset=utf-8' }],
      'cache-control': [{ key: 'Cache-Control', value: 'no-cache, no-store, must-revalidate' }],
    },
    body: `
<!DOCTYPE html>
<html>
<head><title>Authentication Error</title></head>
<body>
  <h1>Authentication Error</h1>
  <p>${message}</p>
  <p><a href="/">Return to homepage</a></p>
</body>
</html>`,
  };
}

/**
 * Create success redirect response with session cookie
 */
function createSuccessResponse(
  redirectUrl: string,
  sessionCookie: string
): CloudFrontResponse {
  return {
    status: '302',
    statusDescription: 'Found',
    headers: {
      location: [{ key: 'Location', value: redirectUrl }],
      'set-cookie': [{ key: 'Set-Cookie', value: sessionCookie }],
      'cache-control': [{ key: 'Cache-Control', value: 'no-cache, no-store, must-revalidate' }],
    },
  };
}

/**
 * Main handler
 */
export async function handler(
  event: CloudFrontRequestEvent
): Promise<CloudFrontResponse> {
  const request = event.Records[0].cf.request;
  const config = getConfig();

  // ACS only accepts POST requests
  if (request.method !== 'POST') {
    return createErrorResponse('400', 'ACS endpoint only accepts POST requests');
  }

  // Get request body
  if (!request.body || !request.body.data) {
    return createErrorResponse('400', 'Missing SAML response');
  }

  // Decode body (might be base64 encoded by CloudFront)
  let body: string;
  if (request.body.encoding === 'base64') {
    body = Buffer.from(request.body.data, 'base64').toString('utf8');
  } else {
    body = request.body.data;
  }

  // Extract SAML response from POST body
  const samlResponse = decodeSamlResponse(body);
  if (!samlResponse) {
    return createErrorResponse('400', 'Missing or invalid SAMLResponse');
  }

  // Get relay state (original URL)
  const relayState = getRelayStateFromBody(body) || config.defaultRedirectUrl;

  try {
    // Initialize SAML providers
    const { idp, sp } = initializeSaml(config.idpMetadataXml, {
      entityId: config.spEntityId,
      acsUrl: `https://${config.cookieDomain}/saml/acs`,
      signAuthnRequests: config.signAuthnRequests,
    });

    // Parse and validate SAML response
    const attributes = await parseSamlResponse(sp, idp, samlResponse);

    if (!attributes.email) {
      return createErrorResponse('400', 'No email found in SAML assertion');
    }

    // Get client IP for session
    const clientIp = getClientIp(request);

    // Create session
    const session = createSession(
      {
        userId: attributes.nameId || attributes.email,
        email: attributes.email,
        displayName: attributes.displayName || attributes.email,
        groups: attributes.groups || [],
        mfaVerified: attributes.mfaAuthenticated || false,
      },
      config.sessionTtlSeconds,
      clientIp
    );

    // Encrypt session into cookie
    const sessionToken = encryptSession(session);
    const sessionCookie = createSessionCookie(
      sessionToken,
      session.expiresAt,
      config.cookieDomain,
      config.cookieName
    );

    console.log(`[ACS] Session created for ${attributes.email} with ${attributes.groups?.length || 0} groups`);

    // Redirect to original URL with session cookie
    return createSuccessResponse(relayState, sessionCookie);

  } catch (error) {
    console.error('[ACS] SAML processing error:', error);

    // Don't expose internal error details
    return createErrorResponse('500', 'Failed to process authentication response');
  }
}
