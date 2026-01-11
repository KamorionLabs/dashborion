# Dashborion Security Architecture

## Overview

Secure multi-method authentication architecture with KMS encryption.

## Authentication Methods

Dashborion supports 4 authentication methods:

| Method | Use Case | Credentials Storage |
|--------|----------|---------------------|
| **Cookie SAML SSO** | Web frontend via IdP | HttpOnly Cookie |
| **Bearer Token (Device Flow)** | CLI after browser auth | `~/.dashborion/` |
| **Bearer Token (Local)** | CLI/API with email/password | `~/.dashborion/` |
| **SigV4 IAM** | CLI with AWS session | AWS credentials |

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           API Gateway                                    │
│                                                                          │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐             │
│  │   Cookie       │  │    Bearer      │  │    SigV4       │             │
│  │  (SAML SSO)    │  │   (Token)      │  │   (IAM)        │             │
│  │                │  │                │  │                │             │
│  │  HttpOnly      │  │  Device Flow   │  │  AWS creds     │             │
│  │  Secure        │  │  or Login      │  │  signed        │             │
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

## Key Concepts: Device Flow vs SSO vs Local

### Device Flow (RFC 8628)

The Device Flow is a **transport mechanism** to obtain a CLI token, not an authentication method per se. It allows the CLI to obtain a token without ever exposing credentials.

```
CLI                          Browser                      API
 │                              │                          │
 ├──POST /device/code──────────────────────────────────────►│
 │◄─────────────────────────────── device_code + user_code──┤
 │                              │                          │
 │  "Go to URL, enter code: XXXX"                          │
 │─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─►│                          │
 │                              ├──Auth (SSO or local)─────►│
 │                              │◄─────────────────session──┤
 │                              ├──POST /device/verify─────►│
 │                              │◄───────────────success────┤
 │                              │                          │
 ├──POST /device/token (poll)──────────────────────────────►│
 │◄───────────────────────────────────────access_token──────┤
```

**Browser authentication** can be:
- **SSO SAML**: Via IdP (Azure AD, Okta, etc.)
- **Local**: Email/password on `/auth/device`

### SSO SAML (web frontend)

```
Browser                     Dashboard                    IdP (Azure AD)
 │                              │                              │
 ├──GET /dashboard─────────────►│                              │
 │◄─────────redirect to IdP─────┤                              │
 ├──────────────────────────────────────────────login──────────►│
 │◄──────────────────────────────────────SAML assertion─────────┤
 ├──POST /saml/acs─────────────►│                              │
 │◄─────────cookie session──────┤                              │
```

### Local Auth (email/password)

```
Client                                                    API
 │                                                         │
 ├──POST /api/auth/login {email, password}─────────────────►│
 │◄─────────────────────────────────── access_token ────────┤
```

### SigV4 IAM Auth

Uses AWS credentials for authentication. Two modes:
- **--use-sso**: Exchange AWS session for Dashborion token (stored)
- **--sigv4**: Identity proof per request via STS (no stored token)

```
CLI (--use-sso)                                           API
 │                                                         │
 ├──POST /api/auth/sso/exchange {aws_credentials}──────────►│
 │◄─────────────────────────────────── access_token ────────┤
 │  (token stored, used as Bearer)                         │

CLI (--sigv4) - Vault-style STS Identity Proof            API                    STS
 │                                                         │                      │
 │  1. Sign GetCallerIdentity request locally              │                      │
 ├──GET /api/... + X-Amz-Iam-Request-* headers────────────►│                      │
 │                                                         ├──Forward to STS──────►│
 │                                                         │◄──Caller identity────┤
 │◄────────────────────────────────────────── data ────────┤                      │
 │  (no token, identity proof per request)                 │                      │
```

#### Vault-style STS Identity Proof (--sigv4)

Uses the same technique as HashiCorp Vault IAM auth:
1. **Client**: Signs a GetCallerIdentity request with AWS credentials
2. **Client**: Sends signed components in HTTP headers:
   - `X-Amz-Iam-Request-Method: POST`
   - `X-Amz-Iam-Request-Url: <base64 encoded STS URL>`
   - `X-Amz-Iam-Request-Body: <base64 encoded request body>`
   - `X-Amz-Iam-Request-Headers: <base64 encoded signed headers>`
3. **Server**: Forwards signed request to AWS STS
4. **STS**: Validates signature and returns caller identity
5. **Server**: Extracts email from Identity Center ARN (session name)

This method works with **HTTP API v2 + REQUEST authorizer** unlike native AWS_IAM which requires REST API v1.

### CLI Options Summary

| Command | Auth | Token Stored |
|---------|------|--------------|
| `dashborion auth login` | Device Flow (SSO/local) | Yes |
| `dashborion auth login --use-sso` | AWS creds exchange | Yes |
| `dashborion --sigv4 <cmd>` | SigV4 per request | No |

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
| Server logs | Token visible | Session ID only |
| Browser history | Token visible | Not visible |
| Referer header | Can leak | Not included |
| XSS attack | Token stealable via JS | Inaccessible to JS |
| CSRF | N/A | Protected by SameSite |

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
// DynamoDB - plaintext data
{
  "pk": "TOKEN#abc123hash",
  "sk": "USER#john@example.com",
  "email": "john@example.com",          // PII in plaintext!
  "permissions": "[{...}]"              // Permissions in plaintext!
}
```

**Proposed (secure):**
```json
// DynamoDB - encrypted data
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

## 3. SigV4 IAM Authentication (Vault-style STS Identity Proof)

### Flow

```
1. User has AWS credentials (IAM user, role, Identity Center SSO)
2. CLI signs a GetCallerIdentity request locally with AWS SigV4:
   - Uses botocore.auth.SigV4Auth
   - Signs for service 'sts', region 'us-east-1'
   - Includes optional X-Dashborion-Server-ID header for replay protection
3. CLI sends signed request components in HTTP headers:
   - X-Amz-Iam-Request-Method: POST
   - X-Amz-Iam-Request-Url: base64(https://sts.amazonaws.com/)
   - X-Amz-Iam-Request-Body: base64(Action=GetCallerIdentity&Version=2011-06-15)
   - X-Amz-Iam-Request-Headers: base64(JSON signed headers)
4. Lambda Authorizer forwards signed request to AWS STS
5. STS validates signature and returns:
   - Arn: arn:aws:sts::123456789012:assumed-role/AWSReservedSSO_.../john@example.com
   - Account: 123456789012
   - UserId: AROA...:john@example.com
6. Authorizer extracts email from Identity Center session name
7. Authorizer looks up user in DynamoDB and returns permissions
```

### Why Vault-style vs AWS_IAM

| Aspect | AWS_IAM (REST API v1) | Vault-style STS (HTTP API v2) |
|--------|----------------------|------------------------------|
| API Type | REST API v1 only | HTTP API v2 compatible |
| Authorizer | IAM auth type on route | REQUEST authorizer |
| Identity | `requestContext.identity.userArn` | Extracted from STS response |
| Validation | API Gateway validates | Server forwards to STS |
| Flexibility | Limited to API Gateway | Works anywhere |

### IAM Identity Extraction

```python
# Pattern for Identity Center roles
# arn:aws:sts::123456789012:assumed-role/AWSReservedSSO_AdministratorAccess_abc123/john@example.com
#                                        ^^^^^^^^^^^^^^^^^^ role name        ^^^^^^^^^^^^^^^^^ email (session name)

# Email extracted from session name if:
# 1. Role name starts with "AWSReservedSSO_"
# 2. Session name matches email pattern ([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})
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

    # 3. Try SigV4 STS Identity Proof (Vault-style)
    if has_identity_proof_headers(event):
        identity = validate_sigv4_sts_auth(headers)  # Forward to STS
        if identity and identity.email:
            user_data = lookup_user(identity.email)
            if user_data:
                return authorize(user_data)

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

### IAM/SigV4 Security

1. **STS Validation**: AWS STS validates the signature server-side
2. **Replay Protection**: Optional X-Dashborion-Server-ID header binds request to specific server
3. **Identity Mapping**: User must exist in DynamoDB (no auto-provision by default)
4. **Audit Trail**: All SigV4 auth attempts logged
5. **Request Freshness**: STS signature includes timestamp (valid ~15 min)

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

### Phase 4: Add SigV4 Auth ✅
1. Implement Vault-style STS identity proof
2. Update authorizer to validate via STS forward
3. Add CLI --sigv4 flag support
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
ENABLE_SIGV4_STS=true
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
    "enableSigv4Sts": true,
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

### SigV4 Auth (Vault-style)
```bash
# Use dashborion CLI with --sigv4 flag
dashborion --sigv4 auth whoami

# Or with specific AWS profile
AWS_PROFILE=my-sso-profile dashborion --sigv4 services list

# Check identity proof generation (debug)
python -c "
from dashborion.utils.sigv4_identity import generate_sts_identity_proof
proof = generate_sts_identity_proof()
print(proof)
"
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

### Python (CLI - SigV4 Identity Proof)

```python
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
import base64
import json

def generate_sts_identity_proof(session, server_id=None):
    """Generate signed GetCallerIdentity request for identity proof."""
    credentials = session.get_credentials().get_frozen_credentials()

    url = 'https://sts.amazonaws.com/'
    body = 'Action=GetCallerIdentity&Version=2011-06-15'

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8',
        'Host': 'sts.amazonaws.com',
    }
    if server_id:
        headers['X-Dashborion-Server-ID'] = server_id

    request = AWSRequest(method='POST', url=url, data=body, headers=headers)

    creds = Credentials(
        access_key=credentials.access_key,
        secret_key=credentials.secret_key,
        token=credentials.token,
    )
    SigV4Auth(creds, 'sts', 'us-east-1').add_auth(request)

    # Convert to headers for transmission
    signed_headers = {k: [str(v)] for k, v in request.headers.items()}

    return {
        'X-Amz-Iam-Request-Method': 'POST',
        'X-Amz-Iam-Request-Url': base64.b64encode(url.encode()).decode(),
        'X-Amz-Iam-Request-Body': base64.b64encode(body.encode()).decode(),
        'X-Amz-Iam-Request-Headers': base64.b64encode(json.dumps(signed_headers).encode()).decode(),
    }
```
