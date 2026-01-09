"""
Authentication & Authorization Data Models
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class DashborionRole(str, Enum):
    """Role levels in Dashborion"""
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"

    @classmethod
    def from_string(cls, value: str) -> "DashborionRole":
        """Convert string to role, defaulting to viewer"""
        try:
            return cls(value.lower())
        except ValueError:
            return cls.VIEWER


@dataclass
class Permission:
    """Permission for a specific project/environment"""
    project: str
    environment: str  # '*' for all environments
    role: DashborionRole
    resources: List[str] = field(default_factory=lambda: ["*"])
    require_mfa: bool = False
    expires_at: Optional[int] = None
    # Source of permission (user, group, or sso)
    source: str = "user"
    source_name: Optional[str] = None  # Group name if from group


@dataclass
class User:
    """User profile stored in DynamoDB"""
    email: str
    display_name: Optional[str] = None
    # Local password hash (argon2 or bcrypt), None for SSO-only users
    password_hash: Optional[str] = None
    # Default role for this user (can be overridden by group/project permissions)
    default_role: DashborionRole = DashborionRole.VIEWER
    # User status
    disabled: bool = False
    # Metadata
    created_at: Optional[int] = None
    created_by: Optional[str] = None
    updated_at: Optional[int] = None
    last_login: Optional[int] = None
    # Local group memberships (SSO groups come from IdP)
    local_groups: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses (excludes sensitive data)"""
        return {
            "email": self.email,
            "displayName": self.display_name,
            "defaultRole": self.default_role.value,
            "disabled": self.disabled,
            "createdAt": self.created_at,
            "createdBy": self.created_by,
            "updatedAt": self.updated_at,
            "lastLogin": self.last_login,
            "localGroups": self.local_groups,
        }


@dataclass
class Group:
    """Group definition with associated permissions"""
    name: str
    description: Optional[str] = None
    # SSO group name for mapping (e.g., "Platform Admins" from Azure AD)
    # This is matched against group names in SAML claims
    sso_group_name: Optional[str] = None
    # SSO group ID for mapping (e.g., Azure AD group object ID) - legacy, prefer name
    sso_group_id: Optional[str] = None
    # Source: 'local' or 'sso'
    source: str = "local"
    # Default role for members of this group
    default_role: DashborionRole = DashborionRole.VIEWER
    # Metadata
    created_at: Optional[int] = None
    created_by: Optional[str] = None
    updated_at: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "name": self.name,
            "description": self.description,
            "ssoGroupName": self.sso_group_name,
            "ssoGroupId": self.sso_group_id,
            "source": self.source,
            "defaultRole": self.default_role.value,
            "createdAt": self.created_at,
            "createdBy": self.created_by,
            "updatedAt": self.updated_at,
        }


@dataclass
class AuthContext:
    """
    Authentication context extracted from Lambda@Edge headers.
    Passed to API handlers for authorization decisions.
    """
    # Identity
    user_id: str
    email: str

    # Authorization
    groups: List[str] = field(default_factory=list)  # Group names (local + SSO)
    sso_groups: List[str] = field(default_factory=list)  # SSO group IDs (for mapping)
    roles: List[DashborionRole] = field(default_factory=list)
    permissions: List[Permission] = field(default_factory=list)

    # Session metadata
    session_id: str = ""
    mfa_verified: bool = False
    auth_method: str = "unknown"  # sso, local, api_key

    @property
    def is_authenticated(self) -> bool:
        """Check if user is authenticated"""
        return bool(self.user_id and self.email)

    @property
    def is_admin(self) -> bool:
        """Check if user has admin role for any project"""
        return DashborionRole.ADMIN in self.roles

    @property
    def is_global_admin(self) -> bool:
        """Check if user has admin role on all projects (*)"""
        for perm in self.permissions:
            if perm.project == "*" and perm.role == DashborionRole.ADMIN:
                return True
        return False

    def has_role(self, role: DashborionRole, project: str = None, environment: str = None) -> bool:
        """Check if user has a specific role"""
        if project is None:
            return role in self.roles

        for perm in self.permissions:
            if perm.role == role:
                if perm.project in [project, "*"]:
                    if environment is None or perm.environment in [environment, "*"]:
                        return True
        return False

    def can_access(self, project: str, environment: str = "*", resource: str = "*") -> bool:
        """Check if user can access a project/environment/resource"""
        for perm in self.permissions:
            if perm.project in [project, "*"]:
                if perm.environment in [environment, "*"]:
                    if resource == "*" or resource in perm.resources or "*" in perm.resources:
                        return True
        return False

    def get_role_for_project(self, project: str, environment: str = "*") -> Optional[DashborionRole]:
        """Get the highest role for a specific project/environment"""
        role_priority = {DashborionRole.ADMIN: 3, DashborionRole.OPERATOR: 2, DashborionRole.VIEWER: 1}
        highest_role = None
        highest_priority = 0

        for perm in self.permissions:
            if perm.project in [project, "*"]:
                if perm.environment in [environment, "*"]:
                    priority = role_priority.get(perm.role, 0)
                    if priority > highest_priority:
                        highest_priority = priority
                        highest_role = perm.role

        return highest_role


class AuthError(Exception):
    """Base class for authentication errors"""
    pass


class UnauthorizedError(AuthError):
    """User is not authenticated"""
    def __init__(self, message: str = "Authentication required"):
        self.message = message
        super().__init__(self.message)


class ForbiddenError(AuthError):
    """User is authenticated but lacks permission"""
    def __init__(self, message: str = "Permission denied"):
        self.message = message
        super().__init__(self.message)


class MfaRequiredError(AuthError):
    """MFA is required for this action"""
    def __init__(self, message: str = "MFA verification required"):
        self.message = message
        super().__init__(self.message)
