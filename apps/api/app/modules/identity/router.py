from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select

from app.core.config import Settings
from app.core.errors import DomainError
from app.modules.authorization.dependencies import (
    Principal,
    SessionDependency,
    require_permission,
)
from app.modules.identity import service
from app.modules.identity.models import AuthSession
from app.modules.identity.schemas import (
    Credentials,
    LoginResult,
    PublicUser,
    RefreshResult,
    Registration,
    SessionPage,
    SessionView,
)
from app.modules.identity.security import (
    check_csrf,
    clear_cookies,
    client_address,
    csrf_cookie,
    decode_access,
    session_cookies,
    unauthorized,
)

router = APIRouter(prefix="/auth", tags=["authentication"])
SessionReader = Annotated[Principal, Depends(require_permission("sessions:read:self"))]
SessionRevoker = Annotated[Principal, Depends(require_permission("sessions:revoke:self"))]


async def cookie_binding(request: Request, db: SessionDependency) -> str:
    config: Settings = request.app.state.settings
    sid = await service.refresh_session_id(db, request.cookies.get(config.refresh_cookie, ""))
    await db.rollback()
    if sid is None:
        try:
            _, sid = decode_access(config, request.cookies.get(config.access_cookie, ""))
        except DomainError:
            pass
    return str(sid) if sid else "anonymous"


@router.get("/csrf", status_code=204)
async def bootstrap(request: Request, response: Response, db: SessionDependency) -> None:
    csrf_cookie(
        response,
        request.app.state.settings,
        await cookie_binding(request, db),
        request.app.state.clock(),
    )


@router.post("/register", status_code=201, response_model=PublicUser)
async def register(
    data: Registration, request: Request, response: Response, db: SessionDependency
) -> PublicUser:
    config: Settings = request.app.state.settings
    at = request.app.state.clock()
    check_csrf(request, config, await cookie_binding(request, db), at)
    await request.app.state.rate_limits.consume(
        "register", client_address(request, config), config.registration_ip_limit, 3600, at
    )
    return await service.register(db, request.app.state.passwords, data)


@router.post("/login", response_model=LoginResult)
async def login(
    data: Credentials, request: Request, response: Response, db: SessionDependency
) -> LoginResult:
    config: Settings = request.app.state.settings
    at = request.app.state.clock()
    check_csrf(request, config, await cookie_binding(request, db), at)
    limiter = request.app.state.rate_limits
    await limiter.consume(
        "login_ip", client_address(request, config), config.login_ip_limit, 900, at
    )
    key = await limiter.consume("login_account", data.email, config.login_account_limit, 900, at)
    user, session, refresh = await service.login(db, request.app.state.passwords, config, data, at)
    await limiter.refund(key)
    session_cookies(response, config, user.id, session.id, refresh, session.expires_at, at)
    return LoginResult(
        user=await service.public_user(db, user),
        access_expires_at=at + timedelta(seconds=config.access_token_seconds),
    )


@router.post("/refresh", response_model=RefreshResult)
async def refresh(request: Request, response: Response, db: SessionDependency) -> RefreshResult:
    config: Settings = request.app.state.settings
    token = request.cookies.get(config.refresh_cookie, "")
    sid = await service.refresh_session_id(db, token)
    # Release the lookup connection before the independent rate-limit transaction.
    await db.rollback()
    if sid is None:
        raise unauthorized()
    at = request.app.state.clock()
    check_csrf(request, config, str(sid), at)
    await request.app.state.rate_limits.consume(
        "refresh", str(sid), config.refresh_session_limit, 60, at
    )
    session, replacement = await service.rotate(db, token, sid, at)
    session_cookies(response, config, session.user_id, sid, replacement, session.expires_at, at)
    return RefreshResult(access_expires_at=at + timedelta(seconds=config.access_token_seconds))


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: SessionDependency) -> None:
    config: Settings = request.app.state.settings
    binding = await cookie_binding(request, db)
    at = request.app.state.clock()
    check_csrf(request, config, binding, at)
    if binding != "anonymous":
        await service.revoke(db, UUID(binding), at)
    clear_cookies(response, config)


@router.get("/sessions", response_model=SessionPage)
async def sessions(
    request: Request,
    db: SessionDependency,
    principal: SessionReader,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SessionPage:
    rows = list(
        (
            await db.scalars(
                select(AuthSession)
                .where(
                    AuthSession.user_id == principal.user.id,
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > request.app.state.clock(),
                )
                .order_by(AuthSession.created_at.desc(), AuthSession.id)
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
    )
    return SessionPage(
        items=[
            SessionView(
                id=row.id,
                created_at=row.created_at,
                expires_at=row.expires_at,
                current=row.id == principal.session.id,
            )
            for row in rows[:limit]
        ],
        next_offset=offset + limit if len(rows) > limit else None,
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke(
    session_id: UUID,
    request: Request,
    response: Response,
    db: SessionDependency,
    principal: SessionRevoker,
) -> None:
    config: Settings = request.app.state.settings
    at = request.app.state.clock()
    check_csrf(request, config, str(principal.session.id), at)
    await service.revoke(db, session_id, at, principal.user.id)
    if session_id == principal.session.id:
        clear_cookies(response, config)


@router.post("/logout-all", status_code=204)
async def logout_all(
    request: Request, response: Response, db: SessionDependency, principal: SessionRevoker
) -> None:
    config: Settings = request.app.state.settings
    at = request.app.state.clock()
    check_csrf(request, config, str(principal.session.id), at)
    rows = (
        await db.scalars(
            select(AuthSession)
            .where(AuthSession.user_id == principal.user.id, AuthSession.revoked_at.is_(None))
            .order_by(AuthSession.id)
            .with_for_update()
        )
    ).all()
    for row in rows:
        row.revoked_at = at
    await db.commit()
    clear_cookies(response, config)
