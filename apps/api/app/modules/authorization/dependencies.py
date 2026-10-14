import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import DomainError
from app.db.session import get_session
from app.modules.authorization.models import Permission, RolePermission, UserRole
from app.modules.identity.models import AuthSession
from app.modules.identity.security import decode_access, unauthorized
from app.modules.users.models import User

SessionDependency = Annotated[AsyncSession, Depends(get_session)]


@dataclass
class Principal:
    user: User
    session: AuthSession
    permissions: list[str]


async def current_user(request: Request, db: SessionDependency) -> Principal:
    config: Settings = request.app.state.settings
    uid, sid = decode_access(config, request.cookies.get(config.access_cookie, ""))
    at = request.app.state.clock()
    row = (
        await db.execute(
            select(User, AuthSession)
            .join(AuthSession, AuthSession.user_id == User.id)
            .where(
                User.id == uid,
                User.active.is_(True),
                AuthSession.id == sid,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > at,
            )
        )
    ).one_or_none()
    if row is None:
        raise unauthorized()
    permissions = list(
        (
            await db.scalars(
                select(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .where(UserRole.user_id == uid)
                .distinct()
                .order_by(Permission.code)
            )
        ).all()
    )
    return Principal(row.User, row.AuthSession, permissions)


PrincipalDependency = Annotated[Principal, Depends(current_user)]


def require_permission(code: str) -> Callable[..., Coroutine[Any, Any, Principal]]:
    async def dependency(principal: PrincipalDependency) -> Principal:
        if code not in principal.permissions:
            logging.getLogger(__name__).info(
                "permission_denied",
                extra={"user_id": str(principal.user.id), "session_id": str(principal.session.id)},
            )
            raise DomainError(403, "forbidden", "Permission required")
        return principal

    return dependency
