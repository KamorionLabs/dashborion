"""
Dashborion Authentication & Authorization Module

Provides middleware and decorators for protecting API endpoints
with permission-based access control.

Also provides Device Flow authentication for CLI clients.
"""

from .models import AuthContext, Permission, DashborionRole, User, Group
from .middleware import authorize_request, get_auth_context
from .decorators import require_permission, require_role, require_admin
from .permissions import (
    check_permission,
    get_user_permissions,
    role_can_perform,
    ROLE_PERMISSIONS,
)
from .handlers import route_auth_request
from .device_flow import validate_token
from .user_management import (
    create_user,
    get_user,
    list_users,
    update_user,
    delete_user,
    create_group,
    get_group,
    get_group_by_sso_id,
    list_groups,
    get_user_effective_permissions,
    verify_user_password,
)

__all__ = [
    # Models
    "AuthContext",
    "Permission",
    "DashborionRole",
    "User",
    "Group",
    # Middleware
    "authorize_request",
    "get_auth_context",
    # Decorators
    "require_permission",
    "require_role",
    "require_admin",
    # Permissions
    "check_permission",
    "get_user_permissions",
    "role_can_perform",
    "ROLE_PERMISSIONS",
    # User/Group Management
    "create_user",
    "get_user",
    "list_users",
    "update_user",
    "delete_user",
    "create_group",
    "get_group",
    "get_group_by_sso_id",
    "list_groups",
    "get_user_effective_permissions",
    "verify_user_password",
    # API Handlers
    "route_auth_request",
    # Token validation (for CLI)
    "validate_token",
]
