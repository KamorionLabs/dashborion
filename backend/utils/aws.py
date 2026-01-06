"""
AWS utility functions for cross-account access and console URLs.
"""

import boto3
from functools import lru_cache
from urllib.parse import quote
from typing import Optional

from config import get_config


@lru_cache(maxsize=32)
def get_cross_account_client(service: str, account_id: str, region: str = None):
    """
    Get boto3 client with cross-account role assumption.
    Results are cached to avoid repeated STS calls.

    Args:
        service: AWS service name (e.g., 'ecs', 'logs')
        account_id: Target AWS account ID
        region: AWS region (defaults to config region)

    Returns:
        boto3 client for the specified service in the target account
    """
    config = get_config()
    region = region or config.region
    shared_account = config.shared_services_account

    # If same account as shared-services, use direct client
    if account_id == shared_account:
        return boto3.client(service, region_name=region)

    # Cross-account: assume read role
    sts = boto3.client('sts')
    role_arn = f"arn:aws:iam::{account_id}:role/{config.project_name}-dashboard-read-role"

    assumed = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName='dashboard-api'
    )

    credentials = assumed['Credentials']
    return boto3.client(
        service,
        region_name=region,
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )


def get_action_client(service: str, account_id: str, user_email: str, region: str = None):
    """
    Get boto3 client with cross-account action role assumption.
    Uses user email in RoleSessionName for CloudTrail attribution.

    Args:
        service: AWS service name
        account_id: Target AWS account ID
        user_email: User email for attribution
        region: AWS region

    Returns:
        boto3 client for write operations
    """
    config = get_config()
    region = region or config.region

    # Sanitize email for role session name
    sanitized_email = user_email.replace('@', '-at-').replace('.', '-dot-')[:64] if user_email else 'unknown'
    session_name = f"dashboard-{sanitized_email}"

    sts = boto3.client('sts')
    role_arn = f"arn:aws:iam::{account_id}:role/{config.project_name}-dashboard-action-role"

    assumed = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName=session_name
    )

    credentials = assumed['Credentials']
    return boto3.client(
        service,
        region_name=region,
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )


def build_sso_console_url(sso_portal_url: str, account_id: str, destination_url: str) -> str:
    """
    Build SSO console shortcut URL for Identity Center.

    Args:
        sso_portal_url: SSO portal base URL
        account_id: Target AWS account ID
        destination_url: Destination console URL

    Returns:
        SSO redirect URL or direct URL if SSO not configured
    """
    if not sso_portal_url:
        return destination_url

    encoded_destination = quote(destination_url, safe='')
    return f"{sso_portal_url}/#/console?account_id={account_id}&destination={encoded_destination}"


def get_user_email(event: dict) -> str:
    """
    Extract user email from SSO header.
    Lambda@Edge adds this header from SSO token.

    Args:
        event: Lambda event

    Returns:
        User email or 'unknown'
    """
    headers = event.get('headers', {})
    return headers.get('x-sso-user-email', headers.get('X-SSO-User-Email', 'unknown'))


def clear_client_cache():
    """Clear the cross-account client cache"""
    get_cross_account_client.cache_clear()
