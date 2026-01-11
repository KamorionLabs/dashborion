"""
SigV4 STS Identity Verification for Lambda Authorizer

Implements Vault-style IAM authentication:
1. Client signs a GetCallerIdentity request with AWS credentials
2. Client sends signed request components in headers
3. Server (this module) forwards request to AWS STS
4. AWS STS validates signature and returns caller identity

Headers expected from client:
- X-Amz-Iam-Request-Method: POST
- X-Amz-Iam-Request-Url: base64-encoded STS URL
- X-Amz-Iam-Request-Body: base64-encoded request body
- X-Amz-Iam-Request-Headers: base64-encoded JSON headers

References:
- https://developer.hashicorp.com/vault/docs/auth/aws
- https://ahermosilla.com/cloud/2020/11/17/leveraging-aws-signed-requests.html
"""

import base64
import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, Any, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


@dataclass
class STSCallerIdentity:
    """Identity returned by STS GetCallerIdentity."""
    arn: str
    account_id: str
    user_id: str
    # Extracted fields
    email: Optional[str] = None
    role_name: Optional[str] = None
    session_name: Optional[str] = None


# Pattern for Identity Center roles
# Example: arn:aws:sts::123456789012:assumed-role/AWSReservedSSO_AdministratorAccess_abc123/john@example.com
IDENTITY_CENTER_ARN_PATTERN = re.compile(
    r'^arn:aws:sts::(\d{12}):assumed-role/(AWSReservedSSO_[^/]+)/(.+)$'
)

# Email pattern
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


def validate_sigv4_sts_auth(headers: Dict[str, str]) -> Optional[STSCallerIdentity]:
    """
    Validate SigV4 authentication by forwarding to AWS STS.

    Extracts signed GetCallerIdentity request from headers and forwards
    it to AWS STS for validation.

    Args:
        headers: Request headers (lowercase keys)

    Returns:
        STSCallerIdentity if valid, None otherwise
    """
    # Check for required headers
    method = headers.get('x-amz-iam-request-method')
    url_b64 = headers.get('x-amz-iam-request-url')
    body_b64 = headers.get('x-amz-iam-request-body')
    headers_b64 = headers.get('x-amz-iam-request-headers')

    if not all([method, url_b64, body_b64, headers_b64]):
        return None

    try:
        # Decode components
        url = base64.b64decode(url_b64).decode('utf-8')
        body = base64.b64decode(body_b64).decode('utf-8')
        signed_headers = json.loads(base64.b64decode(headers_b64).decode('utf-8'))

        # Validate URL is STS
        if 'sts.amazonaws.com' not in url and 'sts.' not in url:
            print(f"[SigV4-STS] Invalid URL (not STS): {url}")
            return None

        # Validate method is POST
        if method.upper() != 'POST':
            print(f"[SigV4-STS] Invalid method: {method}")
            return None

        # Validate body is GetCallerIdentity
        if 'GetCallerIdentity' not in body:
            print(f"[SigV4-STS] Invalid body (not GetCallerIdentity)")
            return None

        # Validate server ID header (replay protection)
        expected_server_id = os.environ.get('DASHBORION_SERVER_ID')
        if expected_server_id:
            server_id_header = signed_headers.get('X-Dashborion-Server-ID', [None])[0]
            if server_id_header != expected_server_id:
                print(f"[SigV4-STS] Server ID mismatch: {server_id_header} != {expected_server_id}")
                return None

        # Forward request to STS
        identity = forward_to_sts(url, method, body, signed_headers)
        if identity:
            print(f"[SigV4-STS] Verified identity: {identity.arn}")
        return identity

    except Exception as e:
        print(f"[SigV4-STS] Validation error: {e}")
        return None


def forward_to_sts(
    url: str,
    method: str,
    body: str,
    signed_headers: Dict[str, list]
) -> Optional[STSCallerIdentity]:
    """
    Forward signed request to AWS STS.

    Args:
        url: STS endpoint URL
        method: HTTP method (POST)
        body: Request body
        signed_headers: Headers in Go-style format (values as lists)

    Returns:
        STSCallerIdentity if successful, None otherwise
    """
    try:
        # Build request
        req = Request(url, data=body.encode('utf-8'), method=method)

        # Add headers (convert from Go-style to standard)
        for key, values in signed_headers.items():
            # Skip Host header - urllib sets it automatically
            if key.lower() == 'host':
                continue
            # Use first value from list
            value = values[0] if values else ''
            req.add_header(key, value)

        # Forward to STS
        with urlopen(req, timeout=10) as response:
            response_body = response.read().decode('utf-8')

        # Parse XML response
        return parse_sts_response(response_body)

    except HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else ''
        print(f"[SigV4-STS] STS returned {e.code}: {error_body[:500]}")
        return None
    except URLError as e:
        print(f"[SigV4-STS] Failed to connect to STS: {e}")
        return None
    except Exception as e:
        print(f"[SigV4-STS] Error forwarding to STS: {e}")
        return None


def parse_sts_response(xml_body: str) -> Optional[STSCallerIdentity]:
    """
    Parse STS GetCallerIdentity XML response.

    Example response:
    <GetCallerIdentityResponse xmlns="https://sts.amazonaws.com/doc/2011-06-15/">
      <GetCallerIdentityResult>
        <Arn>arn:aws:sts::123456789012:assumed-role/AWSReservedSSO_.../email@example.com</Arn>
        <UserId>AROAEXAMPLE:email@example.com</UserId>
        <Account>123456789012</Account>
      </GetCallerIdentityResult>
    </GetCallerIdentityResponse>
    """
    try:
        # Parse XML
        root = ET.fromstring(xml_body)

        # Handle namespace
        ns = {'sts': 'https://sts.amazonaws.com/doc/2011-06-15/'}

        # Find elements (try with and without namespace)
        arn = None
        user_id = None
        account = None

        # Try with namespace
        result = root.find('.//sts:GetCallerIdentityResult', ns)
        if result is not None:
            arn_elem = result.find('sts:Arn', ns)
            user_id_elem = result.find('sts:UserId', ns)
            account_elem = result.find('sts:Account', ns)
            arn = arn_elem.text if arn_elem is not None else None
            user_id = user_id_elem.text if user_id_elem is not None else None
            account = account_elem.text if account_elem is not None else None

        # Fallback: try without namespace
        if not arn:
            for elem in root.iter():
                if elem.tag.endswith('Arn'):
                    arn = elem.text
                elif elem.tag.endswith('UserId'):
                    user_id = elem.text
                elif elem.tag.endswith('Account'):
                    account = elem.text

        if not arn or not account:
            print(f"[SigV4-STS] Missing ARN or Account in response")
            return None

        # Create identity
        identity = STSCallerIdentity(
            arn=arn,
            account_id=account,
            user_id=user_id or '',
        )

        # Extract email from ARN if Identity Center role
        match = IDENTITY_CENTER_ARN_PATTERN.match(arn)
        if match:
            identity.role_name = match.group(2)
            identity.session_name = match.group(3)
            # Session name is email for Identity Center
            if EMAIL_PATTERN.match(identity.session_name):
                identity.email = identity.session_name.lower()

        return identity

    except ET.ParseError as e:
        print(f"[SigV4-STS] Failed to parse STS response: {e}")
        return None
