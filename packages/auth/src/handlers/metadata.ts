/**
 * Metadata Handler - Service Provider Metadata
 *
 * Returns SAML SP metadata XML for IdP configuration.
 */

import type {
  CloudFrontRequestEvent,
  CloudFrontResponse,
} from '../types';
import { initializeSaml, generateSpMetadata } from '../utils/saml';

// Configuration
interface MetadataConfig {
  cloudfrontDomain: string;
  idpMetadataXml: string;
  spEntityId: string;
  signAuthnRequests: boolean;
}

// Load config from environment
function getConfig(): MetadataConfig {
  return {
    cloudfrontDomain: process.env.CLOUDFRONT_DOMAIN || '',
    idpMetadataXml: process.env.IDP_METADATA_XML || '',
    spEntityId: process.env.SP_ENTITY_ID || 'dashborion',
    signAuthnRequests: process.env.SIGN_AUTHN_REQUESTS === 'true',
  };
}

/**
 * Main handler
 */
export async function handler(
  event: CloudFrontRequestEvent
): Promise<CloudFrontResponse> {
  const config = getConfig();

  try {
    // Initialize SAML providers
    const { sp } = initializeSaml(config.idpMetadataXml, {
      entityId: config.spEntityId,
      acsUrl: `https://${config.cloudfrontDomain}/saml/acs`,
      signAuthnRequests: config.signAuthnRequests,
    });

    // Generate SP metadata
    const metadata = generateSpMetadata(sp);

    return {
      status: '200',
      statusDescription: 'OK',
      headers: {
        'content-type': [{ key: 'Content-Type', value: 'application/xml; charset=utf-8' }],
        'cache-control': [{ key: 'Cache-Control', value: 'public, max-age=3600' }],
      },
      body: metadata,
    };

  } catch (error) {
    console.error('[Metadata] Error generating SP metadata:', error);

    return {
      status: '500',
      statusDescription: 'Internal Server Error',
      headers: {
        'content-type': [{ key: 'Content-Type', value: 'text/plain' }],
      },
      body: 'Failed to generate SP metadata',
    };
  }
}
