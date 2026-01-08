/**
 * Dashborion Auth Types
 */

/**
 * Session token stored in encrypted cookie
 */
export interface DashborionSession {
  // Identity
  userId: string;
  email: string;
  displayName: string;

  // Authorization context (from IdP groups)
  groups: string[];
  roles: DashborionRole[];

  // Permissions derived from groups
  permissions: ProjectPermission[];

  // Session metadata
  sessionId: string;
  issuedAt: number;
  expiresAt: number;

  // Security
  mfaVerified: boolean;
  ipAddress: string;
}

/**
 * Role levels in Dashborion
 */
export type DashborionRole = 'viewer' | 'operator' | 'admin';

/**
 * Permission for a specific project/environment
 */
export interface ProjectPermission {
  project: string;
  environment: string; // '*' for all environments
  role: DashborionRole;
  resources: string[]; // '*' for all resources
}

/**
 * SAML configuration from infra.config.json
 */
export interface SamlConfig {
  entityId: string;
  idpMetadataUrl?: string;
  idpMetadataXml?: string;
  signAuthnRequests: boolean;
  wantAssertionsSigned?: boolean;
}

/**
 * Auth configuration from infra.config.json
 */
export interface AuthConfig {
  provider: 'saml' | 'oidc';
  saml?: SamlConfig;
  sessionTtlSeconds: number;
  cookieDomain: string;
  cookieName?: string;
  groupPrefix?: string; // Default: 'dashborion-'
}

/**
 * Encrypted token payload for cookie
 */
export interface EncryptedPayload {
  data: string; // Base64 encoded encrypted data
  iv: string;   // Base64 encoded initialization vector
  tag: string;  // Base64 encoded auth tag (for GCM)
}

/**
 * CloudFront Lambda@Edge request event
 */
export interface CloudFrontRequestEvent {
  Records: Array<{
    cf: {
      config: {
        distributionDomainName: string;
        distributionId: string;
        eventType: string;
        requestId: string;
      };
      request: CloudFrontRequest;
    };
  }>;
}

/**
 * CloudFront request object
 */
export interface CloudFrontRequest {
  uri: string;
  method: string;
  querystring: string;
  headers: CloudFrontHeaders;
  body?: {
    inputTruncated: boolean;
    action: string;
    encoding: string;
    data: string;
  };
  origin?: {
    s3?: {
      domainName: string;
      path: string;
      region: string;
      authMethod: string;
      customHeaders: CloudFrontHeaders;
    };
    custom?: {
      domainName: string;
      port: number;
      protocol: string;
      path: string;
      customHeaders: CloudFrontHeaders;
    };
  };
}

/**
 * CloudFront headers format
 */
export interface CloudFrontHeaders {
  [key: string]: Array<{
    key: string;
    value: string;
  }>;
}

/**
 * CloudFront response object
 */
export interface CloudFrontResponse {
  status: string;
  statusDescription?: string;
  headers?: CloudFrontHeaders;
  body?: string;
  bodyEncoding?: 'text' | 'base64';
}

/**
 * SAML assertion attributes
 */
export interface SamlAttributes {
  email?: string;
  nameId?: string;
  sessionIndex?: string;
  groups?: string[];
  firstName?: string;
  lastName?: string;
  displayName?: string;
  mfaAuthenticated?: boolean;
}

/**
 * Auth context passed to API via headers
 */
export interface AuthHeaders {
  'x-auth-user-id': string;
  'x-auth-user-email': string;
  'x-auth-user-groups': string;
  'x-auth-user-roles': string;
  'x-auth-session-id': string;
  'x-auth-mfa-verified': string;
  'x-auth-permissions': string;
}

/**
 * Role to actions mapping
 */
export const ROLE_PERMISSIONS: Record<DashborionRole, string[]> = {
  viewer: ['read'],
  operator: ['read', 'deploy', 'scale', 'restart', 'invalidate'],
  admin: ['read', 'deploy', 'scale', 'restart', 'invalidate', 'rds-control', 'manage-permissions'],
};

/**
 * Check if a role can perform an action
 */
export function roleCanPerform(role: DashborionRole, action: string): boolean {
  return ROLE_PERMISSIONS[role]?.includes(action) || false;
}

/**
 * Parse IdP group name to extract project and role
 * Format: dashborion-{project}-{role} or dashborion-{project}-{env}-{role}
 */
export function parseGroupName(
  groupName: string,
  prefix: string = 'dashborion-'
): { project: string; environment: string; role: DashborionRole } | null {
  if (!groupName.startsWith(prefix)) {
    return null;
  }

  const parts = groupName.slice(prefix.length).split('-');

  if (parts.length === 2) {
    // dashborion-{project}-{role}
    const [project, roleStr] = parts;
    const role = roleStr as DashborionRole;
    if (['viewer', 'operator', 'admin'].includes(role)) {
      return { project, environment: '*', role };
    }
  } else if (parts.length === 3) {
    // dashborion-{project}-{env}-{role}
    const [project, env, roleStr] = parts;
    const role = roleStr as DashborionRole;
    if (['viewer', 'operator', 'admin'].includes(role)) {
      return { project, environment: env, role };
    }
  }

  return null;
}

/**
 * Derive permissions from IdP groups
 */
export function derivePermissions(
  groups: string[],
  prefix: string = 'dashborion-'
): ProjectPermission[] {
  const permissions: ProjectPermission[] = [];

  for (const group of groups) {
    const parsed = parseGroupName(group, prefix);
    if (parsed) {
      permissions.push({
        project: parsed.project,
        environment: parsed.environment,
        role: parsed.role,
        resources: ['*'],
      });
    }
  }

  return permissions;
}
