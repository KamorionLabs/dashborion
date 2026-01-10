"""
SigV4 IAM Authentication for AWS Identity Center users.

Validates that:
1. The ARN is from an AWS Identity Center role (AWSReservedSSO_*)
2. The account ID is in the allowed organization accounts
3. Extracts email from the session name

This provides passwordless authentication for users already authenticated
via AWS Identity Center SSO.
"""

import os
import re
from typing import Optional, Set
from dataclasses import dataclass


@dataclass
class SigV4Identity:
    """Parsed SigV4 identity from API Gateway."""
    arn: str
    account_id: str
    role_name: str
    session_name: str
    email: Optional[str] = None


# Pattern for Identity Center roles
# Example: arn:aws:sts::123456789012:assumed-role/AWSReservedSSO_AdministratorAccess_abc123/john@example.com
IDENTITY_CENTER_ARN_PATTERN = re.compile(
    r'^arn:aws:sts::(\d{12}):assumed-role/(AWSReservedSSO_[^/]+)/(.+)$'
)

# Email pattern for validation
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


def get_allowed_account_ids() -> Set[str]:
    """
    Get set of allowed AWS account IDs from environment.

    Set via ALLOWED_AWS_ACCOUNT_IDS env var as comma-separated list.
    These should be the accounts in your AWS Organization.
    """
    account_ids_str = os.environ.get('ALLOWED_AWS_ACCOUNT_IDS', '')
    if not account_ids_str:
        return set()

    return {
        aid.strip()
        for aid in account_ids_str.split(',')
        if aid.strip() and aid.strip().isdigit() and len(aid.strip()) == 12
    }


def parse_sigv4_identity(user_arn: str) -> Optional[SigV4Identity]:
    """
    Parse and validate a SigV4 user ARN.

    Only accepts AWS Identity Center (SSO) assumed roles.

    Args:
        user_arn: The userArn from API Gateway requestContext

    Returns:
        SigV4Identity if valid Identity Center role, None otherwise
    """
    if not user_arn:
        return None

    match = IDENTITY_CENTER_ARN_PATTERN.match(user_arn)
    if not match:
        # Not an Identity Center role - reject
        return None

    account_id = match.group(1)
    role_name = match.group(2)
    session_name = match.group(3)

    # Validate account is in allowed list
    allowed_accounts = get_allowed_account_ids()
    if allowed_accounts and account_id not in allowed_accounts:
        print(f"[SigV4] Account {account_id} not in allowed list")
        return None

    # Extract and validate email from session name
    # Identity Center uses email as session name
    email = None
    if EMAIL_PATTERN.match(session_name):
        email = session_name.lower()
    else:
        # Session name is not an email - could be a user ID
        # In this case we can't auto-map to a Dashborion user
        print(f"[SigV4] Session name '{session_name}' is not a valid email")
        return None

    return SigV4Identity(
        arn=user_arn,
        account_id=account_id,
        role_name=role_name,
        session_name=session_name,
        email=email,
    )


def validate_sigv4_auth(
    user_arn: str,
    account_id: str,
) -> Optional[SigV4Identity]:
    """
    Validate SigV4 authentication from API Gateway.

    Args:
        user_arn: event.requestContext.identity.userArn
        account_id: event.requestContext.identity.accountId

    Returns:
        SigV4Identity with email if valid, None otherwise
    """
    identity = parse_sigv4_identity(user_arn)
    if not identity:
        return None

    # Double-check account ID matches
    if identity.account_id != account_id:
        print(f"[SigV4] Account ID mismatch: ARN has {identity.account_id}, context has {account_id}")
        return None

    return identity
