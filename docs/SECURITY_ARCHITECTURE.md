# Dashborion Security Architecture

## Overview

Architecture d'authentification multi-méthodes sécurisée avec chiffrement KMS.

## Authentication Methods

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           API Gateway                                    │
│                                                                          │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐             │
│  │   Cookie       │  │    Bearer      │  │    SigV4       │             │
│  │  (SAML SSO)    │  │ (Device Flow)  │  │   (IAM)        │             │
│  │                │  │                │  │                │             │
│  │  HttpOnly      │  │  CLI tokens    │  │  AWS creds     │             │
│  │  Secure        │  │  stored in     │  │  signed        │             │
│  │  SameSite=Lax  │  │  ~/.dashborion │  │  requests      │             │
│  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘             │
│          │                   │                   │                       │
│          └───────────────────┴───────────────────┘                       │
│                              │                                           │
│                    ┌─────────▼─────────┐                                 │
│                    │    Authorizer     │                                 │
│                    │     Lambda        │                                 │
│                    └─────────┬─────────┘                                 │
│                              │                                           │
└──────────────────────────────┼───────────────────────────────────────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         │                     │                     │
    ┌────▼────┐          ┌─────▼─────┐         ┌────▼────┐
    │ DynamoDB│          │    KMS    │         │   IAM   │
    │ (tokens)│◄────────►│ (encrypt) │         │ (SigV4) │
    └─────────┘          └───────────┘         └─────────┘
```

## 1. Cookie Authentication (SAML SSO)

### Flow

```
1. User clicks "Login with SSO"
2. Frontend redirects to: GET /api/auth/saml/login?returnUrl=...
3. SAML Lambda redirects to IdP
4. User authenticates with IdP
5. IdP POSTs assertion to: POST /api/auth/saml/acs
6. SAML Lambda:
   a. Validates SAML assertion
   b. Creates session in DynamoDB (encrypted with KMS)
   c. Sets HttpOnly cookie with session_id
   d. Redirects to returnUrl (no token in URL!)
7. Frontend calls GET /api/auth/me (cookie sent automatically)
8. Authorizer validates cookie → returns user info
```

### Cookie Structure

```
Set-Cookie: __dashborion_session=<session_id>;
            HttpOnly;
            Secure;
            SameSite=Lax;
            Path=/;
            Domain=.kamorion.cloud;
            Max-Age=3600
```

### Why Cookie > Query String

| Aspect | Query String | Cookie HttpOnly |
|--------|--------------|-----------------|
| Logs serveur | Token visible | Session ID only |
| Historique browser | Token visible | Non visible |
| Header Referer | Peut fuiter | Non inclus |
| XSS attack | Token volable via JS | Inaccessible à JS |
| CSRF | N/A | Protégé par SameSite |

## 2. Bearer Token Authentication (Device Flow)

### Flow (existing, improved)

```
1. CLI: POST /api/auth/device/code
2. Backend creates device_code, returns user_code
3. User opens browser, enters user_code
4. User authenticates (SSO or credentials)
5. CLI polls: POST /api/auth/device/token
6. Backend returns access_token + refresh_token
7. CLI stores tokens in ~/.dashborion/credentials (encrypted)
8. CLI uses: Authorization: Bearer <token>
```

### Improvements with KMS

**Current (insecure):**
```json
// DynamoDB - données en clair
{
  "pk": "TOKEN#abc123hash",
  "sk": "USER#john@example.com",
  "email": "john@example.com",          // PII en clair!
  "permissions": "[{...}]"              // Permissions en clair!
}
```

**Proposed (secure):**
```json
// DynamoDB - données chiffrées
{
  "pk": "TOKEN#abc123hash",
  "sk": "SESSION",
  "encrypted_data": "AQICAHi...",      // KMS encrypted blob
  "key_id": "alias/dashborion-auth",   // KMS key used
  "expires_at": 1234567890
}
```

### Encrypted Data Structure

```json
// Plaintext (before KMS encryption)
{
  "email": "john@example.com",
  "user_id": "john@example.com",
  "permissions": [...],
  "groups": [...],
  "issued_at": 1234567890,
  "client_id": "cli-macos"
}
```

## 3. SigV4 IAM Authentication

### Flow

```
1. User has AWS credentials (IAM user, role, SSO)
2. Request signed with AWS SigV4:
   Authorization: AWS4-HMAC-SHA256
   Credential=AKID.../20240101/eu-west-3/execute-api/aws4_request,
   SignedHeaders=...,
   Signature=...
3. API Gateway validates signature with IAM
4. Authorizer receives IAM identity:
   - event.requestContext.identity.userArn
   - event.requestContext.identity.accountId
5. Authorizer maps IAM identity to Dashborion permissions
```

### IAM Identity Mapping

```python
# Map IAM ARN to Dashborion user
# arn:aws:iam::123456789012:user/john -> john@company.com (via DynamoDB mapping)
# arn:aws:sts::123456789012:assumed-role/DeveloperRole/john -> john@company.com
```

### Configuration in DynamoDB

```json
// IAM mapping table
{
  "pk": "IAM#arn:aws:iam::123456789012:user/john",
  "sk": "MAPPING",
  "email": "john@example.com",
  "auto_provision": false
}

// Or pattern-based mapping
{
  "pk": "IAM_PATTERN#arn:aws:sts::123456789012:assumed-role/DeveloperRole/*",
  "sk": "MAPPING",
  "extract_email_from": "session_name",  // john@example.com from assumed-role/.../john@example.com
  "default_role": "viewer"
}
```

## KMS Key Architecture

### Key Structure

```
┌─────────────────────────────────────────────────────────────┐
│                    KMS Key: dashborion-auth                  │
│                                                              │
│  Alias: alias/dashborion-auth                               │
│  Key Spec: SYMMETRIC_DEFAULT (AES-256-GCM)                  │
│  Key Usage: ENCRYPT_DECRYPT                                  │
│                                                              │
│  Key Policy:                                                 │
│  - Root account: Full admin                                  │
│  - Lambda execution role: Encrypt/Decrypt                    │
│  - No direct user access                                     │
│                                                              │
│  Rotation: Automatic (yearly)                                │
└─────────────────────────────────────────────────────────────┘
```

### What Gets Encrypted

| Data | Location | Encryption |
|------|----------|------------|
| Session data (email, permissions) | DynamoDB tokens table | KMS |
| SAML session cookie value | Cookie | HMAC signature only (session_id is opaque) |
| Refresh tokens | DynamoDB | KMS |
| User PII (email, name) | DynamoDB users table | KMS (optional, adds latency) |
| Audit logs | DynamoDB audit table | KMS (recommended) |

### Encryption Context

```python
# Always use encryption context for additional security
encryption_context = {
    "service": "dashborion",
    "table": "tokens",
    "purpose": "session_data"
}
```

## DynamoDB Schema Updates

### Tokens Table (Updated)

```
pk: TOKEN#{sha256(token)}
sk: SESSION
─────────────────────────────
encrypted_data: bytes (KMS encrypted)
kms_key_id: string
expires_at: number
created_at: number
token_type: string (access|refresh|session)
client_id: string
ttl: number
```

### Sessions Table (New - for Cookie auth)

```
pk: SESSION#{session_id}
sk: META
─────────────────────────────
encrypted_data: bytes (KMS encrypted)
kms_key_id: string
expires_at: number
created_at: number
ip_address: string (hashed)
user_agent_hash: string
ttl: number
```

### IAM Mappings Table (New - for SigV4)

```
pk: IAM#{arn}
sk: MAPPING
─────────────────────────────
email: string
permissions_override: string (optional, KMS encrypted)
created_at: number
created_by: string
```

## Authorizer Logic

```python
def handler(event, context):
    # 1. Try Cookie auth (SAML sessions)
    cookie = get_cookie(event, '__dashborion_session')
    if cookie:
        session = validate_session_cookie(cookie)  # DynamoDB + KMS decrypt
        if session:
            return authorize(session)

    # 2. Try Bearer token (Device flow)
    bearer = get_bearer_token(event)
    if bearer:
        token_data = validate_bearer_token(bearer)  # DynamoDB + KMS decrypt
        if token_data:
            return authorize(token_data)

    # 3. Try SigV4 (IAM)
    iam_arn = event.get('requestContext', {}).get('identity', {}).get('userArn')
    if iam_arn:
        mapping = get_iam_mapping(iam_arn)  # DynamoDB lookup
        if mapping:
            return authorize(mapping)

    # 4. Unauthorized
    return {'isAuthorized': False}
```

## Security Considerations

### Token Security

1. **Token Generation**: `secrets.token_urlsafe(48)` - 384 bits of entropy
2. **Token Storage**: Only SHA256 hash stored, never the raw token
3. **Token Data**: Encrypted with KMS, not readable without key access
4. **Token Rotation**: Access tokens 1h, refresh tokens 30d, sessions 1h

### Cookie Security

1. **HttpOnly**: Not accessible via JavaScript (XSS protection)
2. **Secure**: Only sent over HTTPS
3. **SameSite=Lax**: CSRF protection (allows navigation, blocks cross-site POSTs)
4. **Domain**: `.kamorion.cloud` (shared between frontend and API)

### KMS Security

1. **Key Policy**: Principle of least privilege
2. **Encryption Context**: Binds ciphertext to specific use case
3. **Key Rotation**: Automatic yearly rotation
4. **Audit**: CloudTrail logs all KMS operations

### IAM Security

1. **SigV4 Validation**: AWS handles signature validation
2. **Identity Mapping**: Explicit mapping required (no auto-provision by default)
3. **Audit Trail**: All IAM auth attempts logged

## Migration Plan

### Phase 1: Add KMS Key (non-breaking)
1. Create KMS key via Terraform/SST
2. Add KMS permissions to Lambda role
3. Deploy (no behavior change yet)

### Phase 2: Encrypt New Data
1. Update token storage to encrypt with KMS
2. New tokens use encryption, old tokens still work (backward compatible)
3. Add encryption context validation

### Phase 3: Add Cookie Auth
1. Implement session table
2. Update SAML handler to use cookies
3. Update authorizer to check cookies
4. Frontend updates (remove token from URL handling)

### Phase 4: Add SigV4 Auth
1. Create IAM mappings table
2. Update authorizer to check IAM identity
3. Add mapping management endpoints
4. Document IAM setup for users

### Phase 5: Cleanup
1. Remove x-auth-* header support (Lambda@Edge legacy)
2. Rotate old unencrypted tokens (force re-auth)
3. Enable KMS encryption for users table (optional)

## Configuration

### Environment Variables

```bash
# KMS
KMS_KEY_ARN=arn:aws:kms:eu-west-3:123456789012:key/xxx

# Cookie
COOKIE_DOMAIN=.kamorion.cloud
COOKIE_NAME=__dashborion_session
SESSION_TTL_SECONDS=3600

# Feature flags (for gradual rollout)
ENABLE_COOKIE_AUTH=true
ENABLE_SIGV4_AUTH=true
ENABLE_KMS_ENCRYPTION=true
```

### infra.config.json additions

```json
{
  "auth": {
    "enabled": true,
    "provider": "saml",
    "saml": {...},
    "sessionTtlSeconds": 3600,
    "cookieDomain": ".kamorion.cloud",
    "enableSigv4": true,
    "kms": {
      "keyAlias": "dashborion-auth",
      "enableEncryption": true
    }
  }
}
```

## Testing

### Cookie Auth
```bash
# Login via browser, check cookie is set
# Verify cookie attributes in DevTools
# Test API call with cookie (should work)
# Test API call without cookie (should fail)
```

### Bearer Auth
```bash
# Get token via device flow
dashborion auth login

# Test with token
curl -H "Authorization: Bearer $TOKEN" https://api.../api/me
```

### SigV4 Auth
```bash
# Use AWS CLI with SigV4
aws apigatewayv2 invoke \
  --api-id xxx \
  --stage prod \
  --route-key "GET /api/me" \
  --body '{}'

# Or use awscurl
awscurl --service execute-api \
  --region eu-west-3 \
  https://api.../api/me
```

## Appendix: Crypto Implementation

### Python (Backend)

```python
import boto3
import json
import base64

kms = boto3.client('kms')
KEY_ID = 'alias/dashborion-auth'

def encrypt_data(data: dict, context: dict) -> str:
    """Encrypt data with KMS"""
    plaintext = json.dumps(data).encode('utf-8')
    response = kms.encrypt(
        KeyId=KEY_ID,
        Plaintext=plaintext,
        EncryptionContext=context
    )
    return base64.b64encode(response['CiphertextBlob']).decode('utf-8')

def decrypt_data(encrypted: str, context: dict) -> dict:
    """Decrypt data with KMS"""
    ciphertext = base64.b64decode(encrypted)
    response = kms.decrypt(
        CiphertextBlob=ciphertext,
        EncryptionContext=context
    )
    return json.loads(response['Plaintext'].decode('utf-8'))
```

### TypeScript (SAML Handler)

```typescript
import { KMSClient, EncryptCommand, DecryptCommand } from '@aws-sdk/client-kms';

const kms = new KMSClient({});
const KEY_ID = 'alias/dashborion-auth';

async function encryptData(data: object, context: Record<string, string>): Promise<string> {
  const command = new EncryptCommand({
    KeyId: KEY_ID,
    Plaintext: Buffer.from(JSON.stringify(data)),
    EncryptionContext: context,
  });
  const response = await kms.send(command);
  return Buffer.from(response.CiphertextBlob!).toString('base64');
}

async function decryptData(encrypted: string, context: Record<string, string>): Promise<object> {
  const command = new DecryptCommand({
    CiphertextBlob: Buffer.from(encrypted, 'base64'),
    EncryptionContext: context,
  });
  const response = await kms.send(command);
  return JSON.parse(Buffer.from(response.Plaintext!).toString('utf-8'));
}
```
