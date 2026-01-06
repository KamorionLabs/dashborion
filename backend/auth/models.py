"""
Authentication & Authorization Data Models
"""

from dataclasses import dataclass, field
from typing import List, Optional, Literal
from enum import Enum


class DashborionRole(str, Enum):
    """Role levels in Dashborion"""
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


@dataclass
class Permission:
    """Permission for a specific project/environment"""
    project: str
    environment: str  # '*' for all environments
    role: DashborionRole
    resources: List[str] = field(default_factory=lambda: ["*"])
    require_mfa: bool = False
    expires_at: Optional[int] = None


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
    groups: List[str] = field(default_factory=list)
    roles: List[DashborionRole] = field(default_factory=list)
    permissions: List[Permission] = field(default_factory=list)

    # Session metadata
    session_id: str = ""
    mfa_verified: bool = False

    @property
    def is_authenticated(self) -> bool:
        """Check if user is authenticated"""
        return bool(self.user_id and self.email)

    @property
    def is_admin(self) -> bool:
        """Check if user has admin role for any project"""
        return DashborionRole.ADMIN in self.roles

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
