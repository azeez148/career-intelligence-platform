import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from app.api.health import migration_heads
from app.api.router import router
from app.core.config import Settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.db.session import Database
from app.modules.identity.rate_limits import RateLimits
from app.modules.identity.security import Passwords, now

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()
    configure_logging(config.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.database = Database(config)
        app.state.settings = config
        app.state.migration_heads = migration_heads()
        app.state.clock = now
        app.state.passwords = Passwords(config.password_workers)
        await app.state.passwords.initialize()
        app.state.rate_limits = RateLimits(app.state.database, config)
        try:
            yield
        finally:
            await app.state.database.close()

    app = FastAPI(title="Career Intelligence API", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def request_logging(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = uuid4().hex
        start = perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request.state.request_id
            if request.url.path.startswith(("/api/v1/auth", "/api/v1/users")):
                response.headers["Cache-Control"] = "no-store"
            return response
        finally:
            logger.info(
                "request_completed",
                extra={
                    "request_id": request.state.request_id,
                    "method": request.method,
                    "status_code": status,
                    "duration_ms": round((perf_counter() - start) * 1000, 2),
                },
            )

    register_error_handlers(app)
    app.include_router(router)
    return app
