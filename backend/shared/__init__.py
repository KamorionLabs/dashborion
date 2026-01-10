"""
Shared utilities for Dashborion backend Lambda handlers.

This module provides common functionality used across all Lambda handlers:
- RBAC decorators for permission checking
- API response helpers

Authentication is handled by the Lambda Authorizer.
This module provides authorization (permission checking).
"""

from .rbac import (
    Action,
    ROLE_ACTIONS,
    get_auth_context,
    check_permission,
    is_global_admin,
    require_permission,
    require_global_admin,
    require_authenticated,
)
from .response import (
    json_response,
    error_response,
    success_response,
)

__all__ = [
    # RBAC
    "Action",
    "ROLE_ACTIONS",
    "get_auth_context",
    "check_permission",
    "is_global_admin",
    "require_permission",
    "require_global_admin",
    "require_authenticated",
    # Response
    "json_response",
    "error_response",
    "success_response",
]
