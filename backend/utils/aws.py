"""
AWS utility functions for cross-account access and console URLs.
"""

import boto3
import time
from urllib.parse import quote
from typing import Optional

from app_config import get_config


# Cache for cross-account clients with TTL (50 minutes, credentials expire after 1 hour)
_client_cache = {}
_CACHE_TTL_SECONDS = 50 * 60  # 50 minutes


def get_cross_account_client(
    service: str,
    account_id: str,
    region: str = None,
    project: str = None,
    env: str = None
):
    """
    Get boto3 client with cross-account role assumption.
    Results are cached with TTL to avoid repeated STS calls while respecting token expiration.

    Args:
        service: AWS service name (e.g., 'ecs', 'logs')
        account_id: Target AWS account ID
        region: AWS region (defaults to config region)
        project: Project name (optional, for environment-level role override)
        env: Environment name (optional, for environment-level role override)

    Returns:
        boto3 client for the specified service in the target account
    """
    config = get_config()
    region = region or config.region
    shared_account = config.shared_services_account

    # If same account as shared-services, use direct client (no caching needed)
    if account_id == shared_account:
        return boto3.client(service, region_name=region)

    # Check cache - include project/env in cache key if provided
    cache_key = (service, account_id, region, project, env)
    now = time.time()

    if cache_key in _client_cache:
        cached_client, cached_time = _client_cache[cache_key]
        if now - cached_time < _CACHE_TTL_SECONDS:
            return cached_client
        # Cache expired, remove it
        del _client_cache[cache_key]

    # Get role ARN from config with environment-level override support
    if project and env:
        role_arn = config.get_read_role_arn_for_env(project, env, account_id)
    else:
        role_arn = config.get_read_role_arn(account_id)

    if not role_arn:
        # Fallback to convention-based naming if not in config
        # This handles cases where roles aren't explicitly configured
        role_arn = f"arn:aws:iam::{account_id}:role/dashborion-read-role"

    # Cross-account: assume read role
    sts = boto3.client('sts')
    assumed = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName='dashboard-api'
    )

    credentials = assumed['Credentials']
    client = boto3.client(
        service,
        region_name=region,
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )

    # Cache the client with timestamp
    _client_cache[cache_key] = (client, now)

    return client


def get_action_client(
    service: str,
    account_id: str,
    user_email: str,
    region: str = None,
    project: str = None,
    env: str = None
):
    """
    Get boto3 client with cross-account action role assumption.
    Uses user email in RoleSessionName for CloudTrail attribution.

    Args:
        service: AWS service name
        account_id: Target AWS account ID
        user_email: User email for attribution
        region: AWS region
        project: Project name (optional, for environment-level role override)
        env: Environment name (optional, for environment-level role override)

    Returns:
        boto3 client for write operations
    """
    config = get_config()
    region = region or config.region

    # Sanitize email for role session name
    sanitized_email = user_email.replace('@', '-at-').replace('.', '-dot-')[:64] if user_email else 'unknown'
    session_name = f"dashboard-{sanitized_email}"

    # Get role ARN from config with environment-level override support
    if project and env:
        role_arn = config.get_action_role_arn_for_env(project, env, account_id)
    else:
        role_arn = config.get_action_role_arn(account_id)

    if not role_arn:
        # Fallback to convention-based naming if not in config
        role_arn = f"arn:aws:iam::{account_id}:role/dashborion-action-role"

    sts = boto3.client('sts')
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
    global _client_cache
    _client_cache = {}
