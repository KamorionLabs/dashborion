"""
Shared utilities for Dashborion backend Lambda handlers.

This module provides common functionality used across all Lambda handlers:
- RBAC decorators for permission checking
- API response helpers
"""

from .rbac import (
    Action,
    ROLE_ACTIONS,
    get_auth_context,
    check_permission,
    require_permission,
    require_global_admin,
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
    "require_permission",
    "require_global_admin",
    # Response
    "json_response",
    "error_response",
    "success_response",
]
