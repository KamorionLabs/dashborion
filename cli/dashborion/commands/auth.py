"""
Authentication Commands for Dashborion CLI

Provides commands for:
- login: Authenticate via Device Flow or AWS SSO
- logout: Revoke current token
- whoami: Show current user info
"""

import click
import json
import os
import sys
import time
import webbrowser
from pathlib import Path
from typing import Optional
from datetime import datetime

import requests


# Token storage path
def get_credentials_path() -> Path:
    """Get path to credentials file"""
    return Path.home() / '.dashborion' / 'credentials.json'


def load_credentials() -> Optional[dict]:
    """Load credentials from file"""
    creds_path = get_credentials_path()
    if not creds_path.exists():
        return None

    try:
        with open(creds_path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_credentials(credentials: dict) -> None:
    """Save credentials to file"""
    creds_path = get_credentials_path()
    creds_path.parent.mkdir(parents=True, exist_ok=True)

    # Set restrictive permissions
    with open(creds_path, 'w') as f:
        json.dump(credentials, f, indent=2)

    # Chmod 600 on Unix
    try:
        os.chmod(creds_path, 0o600)
    except (OSError, AttributeError):
        pass  # Windows doesn't support chmod


def delete_credentials() -> bool:
    """Delete credentials file"""
    creds_path = get_credentials_path()
    if creds_path.exists():
        creds_path.unlink()
        return True
    return False


def get_api_base_url() -> str:
    """Get API base URL from config or environment"""
    # Check environment variable
    url = os.environ.get('DASHBORION_API_URL')
    if url:
        return url.rstrip('/')

    # Check config file
    config_path = Path.home() / '.dashborion' / 'config.yaml'
    if config_path.exists():
        try:
            import yaml
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                if config and 'api_url' in config:
                    return config['api_url'].rstrip('/')
        except Exception:
            pass

    # Default
    return 'https://dashboard.homebox.kamorion.cloud'


def is_token_valid(credentials: dict) -> bool:
    """Check if token is still valid"""
    if not credentials:
        return False

    expires_at = credentials.get('expires_at')
    if not expires_at:
        return False

    # Check if expired (with 5 minute buffer)
    return time.time() < (expires_at - 300)


def refresh_token_if_needed(credentials: dict) -> Optional[dict]:
    """Refresh token if expired or expiring soon"""
    if is_token_valid(credentials):
        return credentials

    refresh_token = credentials.get('refresh_token')
    if not refresh_token:
        return None

    api_url = get_api_base_url()

    try:
        response = requests.post(
            f"{api_url}/api/auth/token/refresh",
            json={
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
            },
            timeout=10,
        )

        if response.status_code == 200:
            data = response.json()
            new_credentials = {
                'access_token': data['access_token'],
                'refresh_token': data.get('refresh_token', refresh_token),
                'expires_at': time.time() + data.get('expires_in', 3600),
                'email': credentials.get('email'),
            }
            save_credentials(new_credentials)
            return new_credentials
    except Exception:
        pass

    return None


def get_valid_token() -> Optional[str]:
    """Get a valid access token, refreshing if needed"""
    credentials = load_credentials()
    if not credentials:
        return None

    credentials = refresh_token_if_needed(credentials)
    if not credentials:
        return None

    return credentials.get('access_token')


@click.group()
def auth():
    """Authentication commands"""
    pass


@auth.command()
@click.option('--use-sso', is_flag=True,
              help='Use existing AWS SSO session instead of device flow')
@click.option('--no-browser', is_flag=True,
              help='Do not automatically open browser')
@click.option('--api-url', envvar='DASHBORION_API_URL',
              help='Override API URL')
def login(use_sso: bool, no_browser: bool, api_url: Optional[str]):
    """
    Authenticate with Dashborion

    \b
    Two authentication methods:
      1. Device Flow (default): Opens browser for SSO authentication
      2. AWS SSO (--use-sso): Uses existing AWS SSO session

    \b
    Examples:
      dashborion auth login              # Device flow (opens browser)
      dashborion auth login --use-sso    # Use AWS SSO credentials
      dashborion auth login --no-browser # Show URL to open manually
    """
    api_url = api_url or get_api_base_url()

    if use_sso:
        _login_with_sso(api_url)
    else:
        _login_with_device_flow(api_url, no_browser)


def _login_with_device_flow(api_url: str, no_browser: bool):
    """Authenticate using Device Authorization Flow"""
    click.echo("Initiating device authentication...")

    # Request device code
    try:
        response = requests.post(
            f"{api_url}/api/auth/device/code",
            json={'client_id': 'dashborion-cli'},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        click.echo(f"Error: Failed to connect to API: {e}", err=True)
        sys.exit(1)

    device_code = data['device_code']
    user_code = data['user_code']
    verification_uri = data['verification_uri']
    verification_uri_complete = data.get('verification_uri_complete', f"{verification_uri}?code={user_code}")
    expires_in = data.get('expires_in', 600)
    interval = data.get('interval', 5)

    # Show user instructions
    click.echo()
    click.echo("=" * 60)
    click.echo("  To authenticate, visit:")
    click.echo(f"  {verification_uri}")
    click.echo()
    click.echo(f"  And enter code: {click.style(user_code, bold=True, fg='green')}")
    click.echo("=" * 60)
    click.echo()

    # Open browser if requested
    if not no_browser:
        click.echo("Opening browser...")
        webbrowser.open(verification_uri_complete)

    # Poll for token
    click.echo("Waiting for authentication...", nl=False)
    start_time = time.time()

    while time.time() - start_time < expires_in:
        time.sleep(interval)
        click.echo(".", nl=False)

        try:
            response = requests.post(
                f"{api_url}/api/auth/device/token",
                json={
                    'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
                    'device_code': device_code,
                    'client_id': 'dashborion-cli',
                },
                timeout=10,
            )

            if response.status_code == 200:
                # Success!
                click.echo()
                data = response.json()
                _save_and_display_token(data)
                return

            elif response.status_code == 400:
                error_data = response.json()
                error = error_data.get('error', '')

                if error == 'authorization_pending':
                    continue  # Keep polling
                elif error == 'slow_down':
                    interval += 5  # Slow down polling
                    continue
                elif error == 'expired_token':
                    click.echo()
                    click.echo("Error: Authentication timed out. Please try again.", err=True)
                    sys.exit(1)
                elif error == 'access_denied':
                    click.echo()
                    click.echo("Error: Authentication was denied.", err=True)
                    sys.exit(1)
                else:
                    click.echo()
                    click.echo(f"Error: {error_data.get('error_description', error)}", err=True)
                    sys.exit(1)

        except requests.RequestException as e:
            # Network error, retry
            continue

    click.echo()
    click.echo("Error: Authentication timed out.", err=True)
    sys.exit(1)


def _login_with_sso(api_url: str):
    """Authenticate using existing AWS SSO session"""
    click.echo("Using AWS SSO credentials...")

    try:
        import boto3
    except ImportError:
        click.echo("Error: boto3 is required for AWS SSO login", err=True)
        sys.exit(1)

    try:
        # Get current AWS credentials
        session = boto3.Session()
        credentials = session.get_credentials()

        if not credentials:
            click.echo("Error: No AWS credentials found. Run 'aws sso login' first.", err=True)
            sys.exit(1)

        frozen = credentials.get_frozen_credentials()

        # Exchange for Dashborion token
        response = requests.post(
            f"{api_url}/api/auth/sso/exchange",
            json={
                'aws_access_key_id': frozen.access_key,
                'aws_secret_access_key': frozen.secret_key,
                'aws_session_token': frozen.token,
            },
            timeout=30,
        )

        if response.status_code == 200:
            data = response.json()
            _save_and_display_token(data)
        elif response.status_code == 401:
            error = response.json()
            click.echo(f"Error: {error.get('error_description', 'Invalid AWS credentials')}", err=True)
            click.echo("Hint: Try running 'aws sso login' first", err=True)
            sys.exit(1)
        else:
            click.echo(f"Error: Authentication failed ({response.status_code})", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _save_and_display_token(data: dict):
    """Save token and display success message"""
    credentials = {
        'access_token': data['access_token'],
        'refresh_token': data.get('refresh_token'),
        'expires_at': time.time() + data.get('expires_in', 3600),
        'email': data.get('user', {}).get('email'),
    }

    save_credentials(credentials)

    click.echo()
    click.echo(click.style("Successfully authenticated!", fg='green', bold=True))
    if credentials.get('email'):
        click.echo(f"Logged in as: {credentials['email']}")

    expires = datetime.fromtimestamp(credentials['expires_at'])
    click.echo(f"Token expires: {expires.strftime('%Y-%m-%d %H:%M:%S')}")


@auth.command()
def logout():
    """
    Log out and revoke access token

    Removes stored credentials and revokes the token server-side.
    """
    credentials = load_credentials()

    if not credentials:
        click.echo("Not logged in.")
        return

    api_url = get_api_base_url()
    token = credentials.get('access_token')

    # Try to revoke server-side
    if token:
        try:
            requests.post(
                f"{api_url}/api/auth/token/revoke",
                headers={'Authorization': f'Bearer {token}'},
                timeout=10,
            )
        except requests.RequestException:
            pass  # Ignore errors, we'll delete local credentials anyway

    # Delete local credentials
    delete_credentials()
    click.echo("Logged out successfully.")


@auth.command()
@click.option('--refresh', is_flag=True,
              help='Refresh token if expiring soon')
def whoami(refresh: bool):
    """
    Show current user information

    Displays the currently authenticated user and token status.
    """
    credentials = load_credentials()

    if not credentials:
        click.echo("Not logged in.")
        click.echo()
        click.echo("Run 'dashborion auth login' to authenticate.")
        sys.exit(1)

    # Optionally refresh
    if refresh:
        credentials = refresh_token_if_needed(credentials)
        if credentials:
            click.echo("Token refreshed.")

    # Check validity
    if not is_token_valid(credentials):
        click.echo("Token expired.")
        click.echo()
        click.echo("Run 'dashborion auth login' to re-authenticate.")
        sys.exit(1)

    # Get user info from API
    api_url = get_api_base_url()
    token = credentials.get('access_token')

    try:
        response = requests.get(
            f"{api_url}/api/auth/whoami",
            headers={'Authorization': f'Bearer {token}'},
            timeout=10,
        )

        if response.status_code == 200:
            data = response.json()

            if data.get('authenticated'):
                click.echo(f"Email: {data.get('email')}")
                click.echo(f"Auth method: {data.get('method')}")

                expires = datetime.fromtimestamp(credentials['expires_at'])
                remaining = credentials['expires_at'] - time.time()
                hours = int(remaining // 3600)
                minutes = int((remaining % 3600) // 60)

                click.echo(f"Token expires: {expires.strftime('%Y-%m-%d %H:%M:%S')} ({hours}h {minutes}m remaining)")
            else:
                click.echo("Not authenticated (token may be invalid)")
                sys.exit(1)
        else:
            click.echo(f"Error checking authentication: {response.status_code}")
            sys.exit(1)

    except requests.RequestException as e:
        # Fallback to local info
        click.echo(f"Email: {credentials.get('email', 'unknown')}")
        click.echo("(Could not verify with server)")

        expires = datetime.fromtimestamp(credentials['expires_at'])
        click.echo(f"Token expires: {expires.strftime('%Y-%m-%d %H:%M:%S')}")


@auth.command()
def token():
    """
    Print current access token

    Useful for scripting or debugging. The token is printed to stdout.
    """
    token = get_valid_token()

    if not token:
        click.echo("Not logged in or token expired.", err=True)
        sys.exit(1)

    # Print just the token for scripting
    click.echo(token)


@auth.command()
def status():
    """
    Check authentication status

    \b
    Exit codes:
      0 - Authenticated
      1 - Not authenticated
    """
    credentials = load_credentials()

    if not credentials:
        click.echo("Status: Not logged in")
        sys.exit(1)

    if not is_token_valid(credentials):
        # Try refresh
        credentials = refresh_token_if_needed(credentials)

        if not credentials:
            click.echo("Status: Token expired")
            sys.exit(1)

    click.echo("Status: Authenticated")
    click.echo(f"Email: {credentials.get('email', 'unknown')}")
    sys.exit(0)
