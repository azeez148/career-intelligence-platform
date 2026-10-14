import asyncio
import logging
from pathlib import Path
from typing import Literal

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db.session import Database

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(__name__)


class LiveResponse(BaseModel):
    status: Literal["ok"] = "ok"


class Checks(BaseModel):
    database: Literal["ok", "unavailable"]
    schema_status: Literal["ok", "mismatch", "unknown"] = Field(alias="schema")


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: Checks


def migration_heads() -> set[str]:
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[2] / "migrations")
    )
    return set(ScriptDirectory.from_config(config).get_heads())


async def check_database(database: Database, expected_heads: set[str], deadline: float) -> Checks:
    try:
        async with asyncio.timeout(deadline):
            async with database.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
                exists = await connection.scalar(
                    text("SELECT to_regclass('public.alembic_version')")
                )
                if exists is None:
                    return Checks(database="ok", schema="mismatch")
                result = await connection.execute(text("SELECT version_num FROM alembic_version"))
                current = set(result.scalars().all())
                return Checks(
                    database="ok", schema="ok" if current == expected_heads else "mismatch"
                )
    except Exception as exc:
        logger.warning("readiness_failed", extra={"error_type": type(exc).__name__})
        return Checks(database="unavailable", schema="unknown")


@router.get("/live")
async def live() -> LiveResponse:
    return LiveResponse()


@router.get("/ready", responses={503: {"model": ReadyResponse}})
async def ready(request: Request, response: Response) -> ReadyResponse:
    checks = await check_database(
        request.app.state.database,
        request.app.state.migration_heads,
        request.app.state.settings.db_ready_timeout,
    )
    is_ready = checks.database == "ok" and checks.schema_status == "ok"
    response.status_code = 200 if is_ready else 503
    response.headers["Cache-Control"] = "no-store"
    return ReadyResponse(status="ready" if is_ready else "not_ready", checks=checks)
