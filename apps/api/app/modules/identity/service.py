import logging
import secrets
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import DomainError
from app.modules.authorization.models import Permission, Role, RolePermission, UserRole
from app.modules.identity.models import AuthSession, RefreshToken
from app.modules.identity.schemas import Credentials, PublicUser, Registration
from app.modules.identity.security import Passwords, digest, unauthorized
from app.modules.users.models import User, UserProfile

logger = logging.getLogger(__name__)


async def public_user(db: AsyncSession, user: User) -> PublicUser:
    profile = await db.get(UserProfile, user.id)
    if profile is None:
        raise RuntimeError("User profile missing")
    permissions = list(
        (
            await db.scalars(
                select(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .where(UserRole.user_id == user.id)
                .distinct()
                .order_by(Permission.code)
            )
        ).all()
    )
    return PublicUser(
        id=user.id,
        email=user.email,
        display_name=profile.display_name,
        bio=profile.bio,
        permissions=permissions,
    )


async def register(db: AsyncSession, passwords: Passwords, data: Registration) -> PublicUser:
    encoded = await passwords.hash(data.password.get_secret_value())
    role = await db.scalar(select(Role).where(Role.default_registration.is_(True)))
    if role is None:
        raise DomainError(503, "registration_unavailable", "Registration temporarily unavailable")
    user = User(id=uuid4(), email=data.email, password_hash=encoded, active=True)
    db.add(user)
    try:
        await db.flush()
        db.add_all(
            [
                UserProfile(user_id=user.id, display_name=data.display_name, bio=""),
                UserRole(user_id=user.id, role_id=role.id),
            ]
        )
        await db.flush()
        result = await public_user(db, user)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        if getattr(error.orig, "sqlstate", None) == "23505":
            raise DomainError(
                409, "email_registered", "Email address is already registered"
            ) from None
        raise
    logger.info("user_registered", extra={"user_id": str(user.id)})
    return result


async def login(
    db: AsyncSession, passwords: Passwords, config: Settings, data: Credentials, at: datetime
) -> tuple[User, AuthSession, str]:
    user = await db.scalar(select(User).where(User.email == data.email))
    valid = await passwords.verify(
        user.password_hash if user else None, data.password.get_secret_value()
    )
    if not valid or user is None or not user.active:
        logger.info("login_failed")
        raise DomainError(401, "invalid_credentials", "Email or password is incorrect")
    if passwords.hasher.check_needs_rehash(user.password_hash):
        user.password_hash = await passwords.hash(data.password.get_secret_value())
    session = AuthSession(
        id=uuid4(),
        user_id=user.id,
        created_at=at,
        expires_at=at + timedelta(seconds=config.session_seconds),
    )
    refresh = secrets.token_urlsafe(32)
    db.add(session)
    await db.flush()
    db.add(
        RefreshToken(
            digest=digest(refresh),
            session_id=session.id,
            issued_at=at,
            expires_at=session.expires_at,
        )
    )
    await db.commit()
    logger.info("login_succeeded", extra={"user_id": str(user.id), "session_id": str(session.id)})
    return user, session, refresh


async def refresh_session_id(db: AsyncSession, token: str) -> UUID | None:
    if not token or len(token) > 256:
        return None
    result = await db.scalar(
        select(RefreshToken.session_id).where(RefreshToken.digest == digest(token))
    )
    return UUID(str(result)) if result is not None else None


async def rotate(db: AsyncSession, token: str, sid: UUID, at: datetime) -> tuple[AuthSession, str]:
    session = await db.scalar(select(AuthSession).where(AuthSession.id == sid).with_for_update())
    if session is None or session.revoked_at or session.expires_at <= at:
        raise unauthorized()
    old = await db.scalar(
        select(RefreshToken)
        .where(RefreshToken.digest == digest(token), RefreshToken.session_id == sid)
        .with_for_update()
    )
    if old is None or old.expires_at <= at:
        raise unauthorized()
    if old.consumed_at:
        session.revoked_at = at
        await db.commit()
        logger.warning("refresh_replay", extra={"session_id": str(sid)})
        raise unauthorized()
    user = await db.get(User, session.user_id)
    if user is None or not user.active:
        session.revoked_at = at
        await db.commit()
        raise unauthorized()
    replacement = secrets.token_urlsafe(32)
    old.consumed_at = at
    old.replacement_digest = digest(replacement)
    db.add(
        RefreshToken(
            digest=digest(replacement), session_id=sid, issued_at=at, expires_at=session.expires_at
        )
    )
    await db.commit()
    logger.info("refresh_rotated", extra={"session_id": str(sid)})
    return session, replacement


async def revoke(db: AsyncSession, sid: UUID, at: datetime, owner: UUID | None = None) -> None:
    statement = select(AuthSession).where(AuthSession.id == sid)
    if owner is not None:
        statement = statement.where(AuthSession.user_id == owner)
    session = await db.scalar(statement.with_for_update())
    if session is None:
        raise DomainError(404, "not_found", "Session not found")
    session.revoked_at = session.revoked_at or at
    await db.commit()
    logger.info("session_revoked", extra={"session_id": str(sid)})
