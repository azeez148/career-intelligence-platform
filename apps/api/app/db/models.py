"""Explicit model registration for migration metadata."""

from app.modules.authorization.models import Permission, Role, RolePermission, UserRole
from app.modules.companies.models import Company
from app.modules.discovery.models import CareerSource, DiscoveryCandidate, DiscoveryScan, ScanOutbox
from app.modules.extraction.models import ExtractionOutbox, ExtractionRun
from app.modules.identity.models import AuthRateLimit, AuthSession, RefreshToken
from app.modules.jobs.models import ExtractionRunJob, Job
from app.modules.preferences.models import PreferenceProfile
from app.modules.users.models import User, UserProfile

__all__ = [
    "Company",
    "DiscoveryScan",
    "DiscoveryCandidate",
    "CareerSource",
    "ScanOutbox",
    "ExtractionRun",
    "ExtractionOutbox",
    "Job",
    "ExtractionRunJob",
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
