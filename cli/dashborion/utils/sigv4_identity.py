"""
SigV4 Identity Proof for Dashborion CLI

Uses the same technique as HashiCorp Vault's IAM auth:
1. Client signs a GetCallerIdentity request with AWS credentials
2. Client sends the signed request components to the server
3. Server forwards the request to AWS STS
4. AWS STS validates the signature and returns the caller identity

This provides secure identity verification without transmitting secrets.

References:
- https://developer.hashicorp.com/vault/docs/auth/aws
- https://ahermosilla.com/cloud/2020/11/17/leveraging-aws-signed-requests.html
"""

import base64
import json
from typing import Dict, Optional
from datetime import datetime, timezone


def generate_sts_identity_proof(
    aws_profile: Optional[str] = None,
    server_id: Optional[str] = None,
) -> Dict[str, str]:
    """
    Generate signed GetCallerIdentity request for identity proof.

    Args:
        aws_profile: AWS profile to use (optional)
        server_id: Server ID header for replay attack protection (optional)

    Returns:
        Dict with base64-encoded request components:
        - iam_request_method: HTTP method (POST)
        - iam_request_url: Base64-encoded STS URL
        - iam_request_body: Base64-encoded request body
        - iam_request_headers: Base64-encoded JSON headers
    """
    import boto3
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest

    # Create session with profile if specified
    if aws_profile:
        session = boto3.Session(profile_name=aws_profile)
    else:
        session = boto3.Session()

    credentials = session.get_credentials()
    if not credentials:
        raise ValueError("No AWS credentials available")

    frozen_creds = credentials.get_frozen_credentials()
    region = session.region_name or 'us-east-1'

    # Build GetCallerIdentity request
    # Use global STS endpoint for consistency
    url = 'https://sts.amazonaws.com/'
    body = 'Action=GetCallerIdentity&Version=2011-06-15'

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8',
        'Host': 'sts.amazonaws.com',
    }

    # Add server ID header for replay protection (like Vault's X-Vault-AWS-IAM-Server-ID)
    if server_id:
        headers['X-Dashborion-Server-ID'] = server_id

    # Create AWS request
    request = AWSRequest(method='POST', url=url, data=body, headers=headers)

    # Sign the request
    from botocore.credentials import Credentials
    creds = Credentials(
        access_key=frozen_creds.access_key,
        secret_key=frozen_creds.secret_key,
        token=frozen_creds.token,
    )
    SigV4Auth(creds, 'sts', 'us-east-1').add_auth(request)

    # Prepare signed headers (convert to Go-style format for JSON serialization)
    signed_headers = {}
    for key, value in request.headers.items():
        if isinstance(value, bytes):
            signed_headers[key] = [value.decode('utf-8')]
        else:
            signed_headers[key] = [str(value)]

    # Encode components for transmission
    return {
        'iam_request_method': 'POST',
        'iam_request_url': base64.b64encode(url.encode('utf-8')).decode('ascii'),
        'iam_request_body': base64.b64encode(body.encode('utf-8')).decode('ascii'),
        'iam_request_headers': base64.b64encode(
            json.dumps(signed_headers).encode('utf-8')
        ).decode('ascii'),
    }


def add_identity_proof_headers(
    headers: Dict[str, str],
    aws_profile: Optional[str] = None,
    server_id: Optional[str] = None,
) -> Dict[str, str]:
    """
    Add STS identity proof headers to an existing headers dict.

    Args:
        headers: Existing headers dict to modify
        aws_profile: AWS profile to use
        server_id: Server ID for replay protection

    Returns:
        Modified headers dict with identity proof headers added
    """
    proof = generate_sts_identity_proof(aws_profile, server_id)

    headers['X-Amz-Iam-Request-Method'] = proof['iam_request_method']
    headers['X-Amz-Iam-Request-Url'] = proof['iam_request_url']
    headers['X-Amz-Iam-Request-Body'] = proof['iam_request_body']
    headers['X-Amz-Iam-Request-Headers'] = proof['iam_request_headers']

    return headers
