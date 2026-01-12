/**
 * API Gateway SAML Handler with Cookie-based Sessions
 *
 * Handles SAML authentication via API Gateway with secure cookie sessions.
 * Session data is stored encrypted in DynamoDB using KMS.
 *
 * Endpoints:
 * - GET /api/auth/saml/login - Redirect to IdP
 * - POST /api/auth/saml/acs - Process SAML assertion, set cookie, redirect
 * - GET /api/auth/saml/metadata - SP metadata XML
 */

import type { APIGatewayProxyEventV2, APIGatewayProxyResultV2 } from 'aws-lambda';
import { DynamoDBClient, PutItemCommand, GetItemCommand } from '@aws-sdk/client-dynamodb';
import { KMSClient, EncryptCommand, DecryptCommand } from '@aws-sdk/client-kms';
import { randomUUID, randomBytes, createHash } from 'crypto';
import {
  initializeSaml,
  createLoginRedirectUrl,
  parseSamlResponse,
  decodeSamlResponse,
  getRelayStateFromBody,
  generateSpMetadata,
} from '../utils/saml';

// Clients
const dynamodb = new DynamoDBClient({});
const kms = new KMSClient({});

// Configuration from environment
interface SamlApiConfig {
  apiDomain: string;
  frontendDomain: string;
  cookieDomain: string;
  idpMetadataXml: string;
  spEntityId: string;
  signAuthnRequests: boolean;
  sessionTtlSeconds: number;
  sessionsTableName: string;
  kmsKeyArn: string;
}

function getConfig(): SamlApiConfig {
  return {
    apiDomain: process.env.API_DOMAIN || '',
    frontendDomain: process.env.FRONTEND_DOMAIN || '',
    cookieDomain: process.env.COOKIE_DOMAIN || '',
    idpMetadataXml: process.env.IDP_METADATA_XML || '',
    spEntityId: process.env.SP_ENTITY_ID || 'dashborion',
    signAuthnRequests: process.env.SIGN_AUTHN_REQUESTS === 'true',
    sessionTtlSeconds: parseInt(process.env.SESSION_TTL_SECONDS || '3600', 10),
    sessionsTableName: process.env.TOKENS_TABLE_NAME || 'dashborion-tokens',
    kmsKeyArn: process.env.KMS_KEY_ARN || '',
  };
}

function getAcsUrl(config: SamlApiConfig): string {
  return `https://${config.apiDomain}/api/auth/saml/acs`;
}

// Cookie name
const COOKIE_NAME = '__dashborion_session';

/**
 * Create JSON error response
 */
function errorResponse(statusCode: number, error: string, message: string): APIGatewayProxyResultV2 {
  return {
    statusCode,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*',
    },
    body: JSON.stringify({ error, message }),
  };
}

/**
 * Create redirect response with optional cookie
 */
function redirectResponse(
  location: string,
  cookie?: string
): APIGatewayProxyResultV2 {
  const headers: Record<string, string> = {
    Location: location,
    'Cache-Control': 'no-cache, no-store, must-revalidate',
  };

  if (cookie) {
    headers['Set-Cookie'] = cookie;
  }

  return {
    statusCode: 302,
    headers,
    body: '',
  };
}

/**
 * Generate secure session ID
 */
function generateSessionId(): string {
  return randomBytes(32).toString('base64url');
}

/**
 * Hash session ID for storage (we don't store raw session IDs)
 */
function hashSessionId(sessionId: string): string {
  return createHash('sha256').update(sessionId).digest('hex');
}

/**
 * Encrypt session data with KMS
 */
async function encryptSessionData(
  data: Record<string, unknown>,
  sessionHash: string,
  kmsKeyArn: string
): Promise<string> {
  const plaintext = JSON.stringify(data);

  const command = new EncryptCommand({
    KeyId: kmsKeyArn,
    Plaintext: Buffer.from(plaintext),
    EncryptionContext: {
      service: 'dashborion',
      purpose: 'web_session',
      session_hash: sessionHash.substring(0, 16),
    },
  });

  const response = await kms.send(command);
  return Buffer.from(response.CiphertextBlob!).toString('base64');
}

/**
 * Store session in DynamoDB
 */
async function storeSession(
  sessionId: string,
  sessionData: Record<string, unknown>,
  config: SamlApiConfig,
  ipAddress: string,
  userAgent: string
): Promise<void> {
  const sessionHash = hashSessionId(sessionId);
  const now = Math.floor(Date.now() / 1000);
  const expiresAt = now + config.sessionTtlSeconds;

  // Encrypt sensitive data
  const encryptedData = await encryptSessionData(sessionData, sessionHash, config.kmsKeyArn);

  const command = new PutItemCommand({
    TableName: config.sessionsTableName,
    Item: {
      pk: { S: `SESSION#${sessionHash}` },
      sk: { S: 'META' },
      encrypted_data: { S: encryptedData },
      expires_at: { N: String(expiresAt) },
      created_at: { N: String(now) },
      ip_hash: { S: createHash('sha256').update(ipAddress).digest('hex').substring(0, 16) },
      ua_hash: { S: createHash('sha256').update(userAgent).digest('hex').substring(0, 16) },
      ttl: { N: String(expiresAt + 86400) }, // Keep 1 day after expiry for audit
    },
  });

  await dynamodb.send(command);
}

/**
 * Build secure cookie string
 */
function buildCookie(
  sessionId: string,
  config: SamlApiConfig
): string {
  const parts = [
    `${COOKIE_NAME}=${sessionId}`,
    'HttpOnly',
    'Secure',
    'SameSite=None',  // Must be None for cross-origin cookie (frontend → API)
    'Path=/',
    `Max-Age=${config.sessionTtlSeconds}`,
  ];

  if (config.cookieDomain) {
    parts.push(`Domain=${config.cookieDomain}`);
  }

  return parts.join('; ');
}

/**
 * Handle GET /api/auth/saml/login
 * Redirects to IdP for authentication
 */
async function handleLogin(event: APIGatewayProxyEventV2): Promise<APIGatewayProxyResultV2> {
  const config = getConfig();

  if (!config.idpMetadataXml) {
    return errorResponse(500, 'configuration_error', 'SAML not configured');
  }

  // Get return URL from query params
  const returnUrl = event.queryStringParameters?.returnUrl || `https://${config.frontendDomain}/`;

  try {
    const { idp, sp } = initializeSaml(config.idpMetadataXml, {
      entityId: config.spEntityId,
      acsUrl: getAcsUrl(config),
      signAuthnRequests: config.signAuthnRequests,
    });

    // Create login redirect URL with returnUrl as RelayState
    const loginUrl = createLoginRedirectUrl(sp, idp, returnUrl);

    console.log('[SAML Login] Redirecting to IdP, RelayState:', returnUrl);

    return redirectResponse(loginUrl);
  } catch (error) {
    console.error('[SAML Login] Error:', error);
    return errorResponse(500, 'saml_error', 'Failed to initiate SAML login');
  }
}

/**
 * Handle POST /api/auth/saml/acs
 * Processes SAML assertion, creates session, sets cookie, redirects to frontend
 */
async function handleAcs(event: APIGatewayProxyEventV2): Promise<APIGatewayProxyResultV2> {
  const config = getConfig();

  if (!config.idpMetadataXml) {
    return errorResponse(500, 'configuration_error', 'SAML not configured');
  }

  if (!config.kmsKeyArn) {
    return errorResponse(500, 'configuration_error', 'KMS key not configured');
  }

  // Get body
  let body = event.body || '';
  if (event.isBase64Encoded) {
    body = Buffer.from(body, 'base64').toString('utf8');
  }

  console.log('[SAML ACS] Received body length:', body.length);

  // Extract SAML response
  const samlResponse = decodeSamlResponse(body);
  if (!samlResponse) {
    console.error('[SAML ACS] No SAMLResponse in body');
    return errorResponse(400, 'invalid_request', 'Missing SAMLResponse');
  }

  // Get relay state (return URL)
  const relayState = getRelayStateFromBody(body) || `https://${config.frontendDomain}/`;
  console.log('[SAML ACS] RelayState:', relayState);

  try {
    const { idp, sp } = initializeSaml(config.idpMetadataXml, {
      entityId: config.spEntityId,
      acsUrl: getAcsUrl(config),
      signAuthnRequests: config.signAuthnRequests,
    });

    // Parse and validate SAML response
    const attributes = await parseSamlResponse(sp, idp, samlResponse);

    if (!attributes.email) {
      console.error('[SAML ACS] No email in assertion');
      return errorResponse(400, 'invalid_assertion', 'No email found in SAML assertion');
    }

    console.log('[SAML ACS] Authenticated:', attributes.email, 'Groups:', attributes.groups?.length || 0);

    // Get client info
    const clientIp = event.requestContext?.http?.sourceIp || 'unknown';
    const userAgent = event.headers?.['user-agent'] || 'unknown';

    // Generate session ID
    const sessionId = generateSessionId();

    // Session data to encrypt
    const sessionData = {
      userId: attributes.nameId || attributes.email,
      email: attributes.email.toLowerCase(),
      displayName: attributes.displayName || attributes.email,
      groups: attributes.groups || [],
      mfaVerified: attributes.mfaAuthenticated || false,
      sessionId: randomUUID(),
      issuedAt: Math.floor(Date.now() / 1000),
    };

    // Store session in DynamoDB
    await storeSession(sessionId, sessionData, config, clientIp, userAgent);

    // Build cookie
    const cookie = buildCookie(sessionId, config);

    // Redirect to frontend (no token in URL!)
    console.log('[SAML ACS] Session created, redirecting to:', relayState);

    return redirectResponse(relayState, cookie);
  } catch (error) {
    console.error('[SAML ACS] Error processing assertion:', error);
    return errorResponse(500, 'saml_error', 'Failed to process SAML assertion');
  }
}

/**
 * Handle GET /api/auth/saml/metadata
 * Returns SP metadata XML
 */
async function handleMetadata(): Promise<APIGatewayProxyResultV2> {
  const config = getConfig();

  if (!config.idpMetadataXml) {
    return errorResponse(500, 'configuration_error', 'SAML not configured');
  }

  try {
    const { sp } = initializeSaml(config.idpMetadataXml, {
      entityId: config.spEntityId,
      acsUrl: getAcsUrl(config),
      signAuthnRequests: config.signAuthnRequests,
    });

    const metadata = generateSpMetadata(sp);

    return {
      statusCode: 200,
      headers: {
        'Content-Type': 'application/xml; charset=utf-8',
        'Cache-Control': 'public, max-age=3600',
      },
      body: metadata,
    };
  } catch (error) {
    console.error('[SAML Metadata] Error:', error);
    return errorResponse(500, 'saml_error', 'Failed to generate SP metadata');
  }
}

/**
 * Main handler - routes to specific handlers
 */
export async function handler(event: APIGatewayProxyEventV2): Promise<APIGatewayProxyResultV2> {
  const method = event.requestContext?.http?.method || 'GET';
  const path = event.rawPath || '';

  console.log(`[SAML API] ${method} ${path}`);

  // Route to handlers
  if (path === '/api/auth/saml/login' && method === 'GET') {
    return handleLogin(event);
  }

  if (path === '/api/auth/saml/acs' && method === 'POST') {
    return handleAcs(event);
  }

  if (path === '/api/auth/saml/metadata' && method === 'GET') {
    return handleMetadata();
  }

  return errorResponse(404, 'not_found', `Unknown SAML endpoint: ${method} ${path}`);
}
