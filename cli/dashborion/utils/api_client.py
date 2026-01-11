"""
API Client for Dashborion CLI

Supports multiple authentication methods:
- Bearer token (from login)
- AWS SigV4 Identity Proof (forward signed GetCallerIdentity to STS)

The SigV4 method uses the same technique as HashiCorp Vault's IAM auth:
1. Client signs a GetCallerIdentity request with AWS credentials
2. Client sends signed request components to the server
3. Server forwards to AWS STS for identity verification

Usage:
    from dashborion.utils.api_client import get_api_client, set_sigv4_mode

    # Enable SigV4 mode globally
    set_sigv4_mode(True)

    # Get configured client
    client = get_api_client()
    response = client.get('/api/services/list', params={'env': 'staging'})
"""

import os
from typing import Optional, Dict, Any
from urllib.parse import urlparse

import requests

# Global flag for SigV4 mode
_sigv4_mode = False
_aws_profile = None


def set_sigv4_mode(enabled: bool, profile: Optional[str] = None):
    """Enable or disable SigV4 signing for all requests."""
    global _sigv4_mode, _aws_profile
    _sigv4_mode = enabled
    _aws_profile = profile


def is_sigv4_mode() -> bool:
    """Check if SigV4 mode is enabled."""
    return _sigv4_mode


class APIClient:
    """HTTP client for Dashborion API with auth support."""

    def __init__(self, base_url: str, use_sigv4: bool = False, aws_profile: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.use_sigv4 = use_sigv4
        self.aws_profile = aws_profile

    def _get_bearer_headers(self) -> Dict[str, str]:
        """Get Bearer token headers."""
        from dashborion.commands.auth import get_valid_token
        token = get_valid_token()
        if not token:
            raise AuthenticationError("Not authenticated. Run 'dashborion auth login' first.")
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }

    def _get_sigv4_headers(self) -> Dict[str, str]:
        """
        Get SigV4 identity proof headers.

        Uses the Vault-style IAM auth technique:
        - Signs a GetCallerIdentity request with AWS credentials
        - Sends signed request components in headers
        - Server forwards to STS for verification
        """
        from dashborion.utils.sigv4_identity import add_identity_proof_headers

        headers = {'Content-Type': 'application/json'}

        # Extract server hostname for replay protection
        parsed = urlparse(self.base_url)
        server_id = parsed.netloc

        try:
            add_identity_proof_headers(
                headers,
                aws_profile=self.aws_profile,
                server_id=server_id,
            )
        except Exception as e:
            raise AuthenticationError(f"Failed to generate SigV4 identity proof: {e}")

        return headers

    def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
    ) -> requests.Response:
        """Make authenticated API request."""
        url = f"{self.base_url}{path}"

        if self.use_sigv4:
            # SigV4 identity proof (Vault-style)
            headers = self._get_sigv4_headers()
            return requests.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_data,
                timeout=timeout,
            )
        else:
            # Bearer token
            headers = self._get_bearer_headers()
            return requests.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_data,
                timeout=timeout,
            )

    def get(self, path: str, params: Optional[Dict[str, Any]] = None, **kwargs) -> requests.Response:
        """GET request."""
        return self.request('GET', path, params=params, **kwargs)

    def post(self, path: str, json_data: Optional[Dict[str, Any]] = None, **kwargs) -> requests.Response:
        """POST request."""
        return self.request('POST', path, json_data=json_data, **kwargs)

    def put(self, path: str, json_data: Optional[Dict[str, Any]] = None, **kwargs) -> requests.Response:
        """PUT request."""
        return self.request('PUT', path, json_data=json_data, **kwargs)

    def delete(self, path: str, json_data: Optional[Dict[str, Any]] = None, **kwargs) -> requests.Response:
        """DELETE request."""
        return self.request('DELETE', path, json_data=json_data, **kwargs)


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass


def get_api_client() -> APIClient:
    """Get configured API client."""
    from dashborion.commands.auth import get_api_base_url

    api_url = get_api_base_url()
    return APIClient(
        base_url=api_url,
        use_sigv4=_sigv4_mode,
        aws_profile=_aws_profile,
    )
