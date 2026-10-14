from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.modules.authorization.dependencies import Principal, SessionDependency, require_permission
from app.modules.identity.schemas import PublicUser
from app.modules.identity.security import check_csrf
from app.modules.identity.service import public_user
from app.modules.users.models import UserProfile
from app.modules.users.schemas import ProfileUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=PublicUser)
async def me(
    db: SessionDependency,
    principal: Annotated[Principal, Depends(require_permission("profile:read:self"))],
) -> PublicUser:
    return await public_user(db, principal.user)


@router.patch("/me/profile", response_model=PublicUser)
async def update_profile(
    data: ProfileUpdate,
    request: Request,
    db: SessionDependency,
    principal: Annotated[Principal, Depends(require_permission("profile:update:self"))],
) -> PublicUser:
    check_csrf(
        request, request.app.state.settings, str(principal.session.id), request.app.state.clock()
    )
    profile = await db.get(UserProfile, principal.user.id)
    if profile is None:
        raise RuntimeError("User profile missing")
    profile.display_name, profile.bio = data.display_name, data.bio
    await db.commit()
    return await public_user(db, principal.user)
