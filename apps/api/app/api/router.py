from fastapi import APIRouter

from app.api.health import router as health_router
from app.modules.companies.router import router as companies_router
from app.modules.identity.router import router as identity_router
from app.modules.preferences.router import router as preferences_router
from app.modules.users.router import router as users_router

router = APIRouter(prefix="/api/v1")
router.include_router(health_router)
router.include_router(identity_router)
router.include_router(users_router)
router.include_router(companies_router)
router.include_router(preferences_router)
