/**
 * SAML utilities for processing SAML assertions
 *
 * Uses samlify library for SAML parsing and validation.
 */

import * as samlify from 'samlify';
import type { SamlConfig, SamlAttributes } from '../types';

// Disable XML schema validation (too slow for Lambda@Edge)
samlify.setSchemaValidator({
  validate: () => Promise.resolve('skipped'),
});

/**
 * Create Identity Provider from metadata
 */
export function createIdentityProvider(idpMetadataXml: string): samlify.IdentityProviderInstance {
  return samlify.IdentityProvider({
    metadata: idpMetadataXml,
    wantLogoutRequestSigned: false,
  });
}

/**
 * Create Service Provider
 */
export function createServiceProvider(config: {
  entityId: string;
  acsUrl: string;
  signAuthnRequests: boolean;
  privateKey?: string;
  certificate?: string;
}): samlify.ServiceProviderInstance {
  const spConfig: samlify.ServiceProviderSettings = {
    entityID: config.entityId,
    assertionConsumerService: [
      {
        Binding: samlify.Constants.namespace.binding.post,
        Location: config.acsUrl,
      },
    ],
    wantAssertionsSigned: true,
    wantMessageSigned: false,
    authnRequestsSigned: config.signAuthnRequests,
  };

  // Add signing key if requests should be signed
  if (config.signAuthnRequests && config.privateKey && config.certificate) {
    spConfig.privateKey = config.privateKey;
    spConfig.signingCert = config.certificate;
  }

  return samlify.ServiceProvider(spConfig);
}

/**
 * Create SAML AuthnRequest URL for redirect
 */
export function createLoginRedirectUrl(
  sp: samlify.ServiceProviderInstance,
  idp: samlify.IdentityProviderInstance,
  relayState: string
): string {
  const { context } = sp.createLoginRequest(idp, 'redirect');

  // Add relay state to preserve original URL
  const url = new URL(context);
  url.searchParams.set('RelayState', relayState);

  return url.toString();
}

/**
 * Parse SAML Response and extract user attributes
 */
export async function parseSamlResponse(
  sp: samlify.ServiceProviderInstance,
  idp: samlify.IdentityProviderInstance,
  samlResponse: string
): Promise<SamlAttributes> {
  const result = await sp.parseLoginResponse(idp, 'post', {
    body: { SAMLResponse: samlResponse },
  });

  const { extract } = result;

  // Extract attributes from SAML assertion
  const attributes: SamlAttributes = {
    nameId: extract.nameID,
    sessionIndex: extract.sessionIndex?.sessionIndex,
    email: undefined,
    groups: [],
    displayName: undefined,
    mfaAuthenticated: false,
  };

  // Parse attributes from assertion
  const attrs = extract.attributes || {};

  // Email - try multiple common attribute names
  attributes.email =
    attrs['http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress'] ||
    attrs['email'] ||
    attrs['Email'] ||
    attrs['mail'] ||
    extract.nameID;

  // Display name
  attributes.displayName =
    attrs['http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name'] ||
    attrs['displayName'] ||
    attrs['name'] ||
    attrs['Name'] ||
    attributes.email;

  // First and last name
  attributes.firstName =
    attrs['http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname'] ||
    attrs['firstName'] ||
    attrs['givenName'];

  attributes.lastName =
    attrs['http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname'] ||
    attrs['lastName'] ||
    attrs['surname'];

  // Groups - AWS Identity Center uses memberOf or groups
  const groupsAttr =
    attrs['https://aws.amazon.com/SAML/Attributes/AccessControl:groups'] ||
    attrs['memberOf'] ||
    attrs['groups'] ||
    attrs['Group'] ||
    [];

  if (Array.isArray(groupsAttr)) {
    attributes.groups = groupsAttr;
  } else if (typeof groupsAttr === 'string') {
    attributes.groups = groupsAttr.split(',').map((g) => g.trim());
  }

  // MFA status - check authentication context
  const authnContext = extract.attributes?.['AuthnContextClassRef'] || '';
  attributes.mfaAuthenticated =
    authnContext.includes('MultiFactorAuthentication') ||
    authnContext.includes('MobileOneFactorUnregistered') ||
    attrs['mfaAuthenticated'] === 'true';

  return attributes;
}

/**
 * Generate Service Provider metadata XML
 */
export function generateSpMetadata(
  sp: samlify.ServiceProviderInstance
): string {
  return sp.getMetadata();
}

/**
 * Decode base64 SAML response from POST body
 */
export function decodeSamlResponse(body: string): string | null {
  try {
    // Parse URL-encoded body
    const params = new URLSearchParams(body);
    const samlResponse = params.get('SAMLResponse');

    if (!samlResponse) {
      return null;
    }

    // The response is already URL-decoded by URLSearchParams
    // but might need to handle + to space conversion
    return samlResponse.replace(/\+/g, ' ');
  } catch (error) {
    console.error('Failed to decode SAML response:', error);
    return null;
  }
}

/**
 * Get RelayState from POST body
 */
export function getRelayStateFromBody(body: string): string | null {
  try {
    const params = new URLSearchParams(body);
    return params.get('RelayState');
  } catch {
    return null;
  }
}

/**
 * Cache for IDP metadata to avoid parsing repeatedly
 */
let cachedIdp: samlify.IdentityProviderInstance | null = null;
let cachedSp: samlify.ServiceProviderInstance | null = null;

/**
 * Initialize SAML providers (call once at startup or cache in Lambda)
 */
export function initializeSaml(
  idpMetadataXml: string,
  spConfig: {
    entityId: string;
    acsUrl: string;
    signAuthnRequests: boolean;
  }
): { idp: samlify.IdentityProviderInstance; sp: samlify.ServiceProviderInstance } {
  if (!cachedIdp) {
    cachedIdp = createIdentityProvider(idpMetadataXml);
  }

  if (!cachedSp) {
    cachedSp = createServiceProvider(spConfig);
  }

  return { idp: cachedIdp, sp: cachedSp };
}

/**
 * Clear cached SAML providers (for testing)
 */
export function clearSamlCache(): void {
  cachedIdp = null;
  cachedSp = null;
}
