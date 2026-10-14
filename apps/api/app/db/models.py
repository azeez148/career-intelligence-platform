"""Explicit model registration for migration metadata."""

from app.modules.authorization.models import Permission, Role, RolePermission, UserRole
from app.modules.companies.models import Company
from app.modules.identity.models import AuthRateLimit, AuthSession, RefreshToken
from app.modules.preferences.models import PreferenceProfile
from app.modules.users.models import User, UserProfile

__all__ = [
    "Company",
    "PreferenceProfile",
    "Permission",
    "Role",
    "RolePermission",
    "UserRole",
    "AuthRateLimit",
    "AuthSession",
    "RefreshToken",
    "User",
    "UserProfile",
]
