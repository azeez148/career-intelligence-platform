from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from test_postgres import POSTGRES_IMAGE, migrate
from testcontainers.community.postgres import PostgresContainer

from app.core.config import Settings
from app.db.session import Database

pytestmark = pytest.mark.integration


async def test_phase5_upgrade_preserves_jobs_and_preferences_then_downgrades():
    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as container:
        url = container.get_connection_url()
        migrate(url, "upgrade", "0005_job_extraction")
        db = Database(Settings(database_url=SecretStr(url)))
        uid, pid = UUID(int=500), UUID(int=501)
        try:
            async with db.sessions() as session, session.begin():
                await session.execute(
                    text(
                        "INSERT INTO users(id,email,password_hash,active) "
                        "VALUES (:id,'phase5@example.com','fixture-hash',true)"
                    ),
                    {"id": uid},
                )
                await session.execute(
                    text(
                        "INSERT INTO preference_profiles(id,user_id,name,name_key,criteria) "
                        "VALUES (:pid,:uid,'Kept','kept','{}'::jsonb)"
                    ),
                    {"pid": pid, "uid": uid},
                )
            migrate(url, "upgrade", "head")
            migrate(url, "upgrade", "head")
            migrate(url, "check")
            async with db.sessions() as session:
                assert await session.scalar(text("SELECT count(*) FROM permissions")) == 20
                granted = await session.scalar(
                    text(
                        "SELECT count(*) FROM role_permissions rp JOIN permissions p "
                        "ON p.id = rp.permission_id WHERE rp.role_id = :member AND p.code IN "
                        "('matches:read:self','matches:update:self','ai:use:self')"
                    ),
                    {"member": UUID(int=1)},
                )
                assert granted == 3
            migrate(url, "downgrade", "0005_job_extraction")
            async with db.sessions() as session:
                assert await session.scalar(text("SELECT count(*) FROM permissions")) == 17
                assert (
                    await session.scalar(
                        text("SELECT count(*) FROM preference_profiles WHERE id=:pid"),
                        {"pid": pid},
                    )
                    == 1
                )
                for table in ("job_matches", "match_runs", "ai_assessments", "ai_usage"):
                    assert (
                        await session.scalar(text(f"SELECT to_regclass('public.{table}')")) is None
                    )
            migrate(url, "upgrade", "head")
            migrate(url, "check")
        finally:
            await db.close()
