from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from test_postgres import POSTGRES_IMAGE, migrate
from testcontainers.community.postgres import PostgresContainer

from app.core.config import Settings
from app.db.session import Database

pytestmark = pytest.mark.integration


async def test_phase4_upgrade_preserves_discovery_and_custom_roles_then_downgrades():
    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as container:
        url = container.get_connection_url()
        migrate(url, "upgrade", "0004_career_discovery")
        db = Database(Settings(database_url=SecretStr(url)))
        uid, rid, cid, sid = UUID(int=400), UUID(int=401), UUID(int=402), UUID(int=403)
        try:
            async with db.sessions() as session, session.begin():
                await session.execute(
                    text(
                        "INSERT INTO users(id,email,password_hash,active) "
                        "VALUES (:id,'phase4@example.com','fixture-hash',true)"
                    ),
                    {"id": uid},
                )
                await session.execute(
                    text(
                        "INSERT INTO companies(id,user_id,name,identity_key) "
                        "VALUES (:cid,:uid,'Preserved','preserved')"
                    ),
                    {"cid": cid, "uid": uid},
                )
                await session.execute(
                    text(
                        "INSERT INTO discovery_scans(id,user_id,company_id,status) "
                        "VALUES (:sid,:uid,:cid,'succeeded')"
                    ),
                    {"sid": sid, "uid": uid, "cid": cid},
                )
                await session.execute(
                    text(
                        "INSERT INTO roles(id,code,description,default_registration) "
                        "VALUES (:id,'phase4-custom','Custom',false)"
                    ),
                    {"id": rid},
                )
            migrate(url, "upgrade", "0005_job_extraction")
            migrate(url, "upgrade", "0005_job_extraction")
            async with db.sessions() as session:
                assert await session.scalar(text("SELECT count(*) FROM permissions")) == 17
                assert (
                    await session.scalar(
                        text(
                            "SELECT count(*) FROM role_permissions rp JOIN permissions p "
                            "ON p.id = rp.permission_id WHERE rp.role_id = :member "
                            "AND p.code IN ('jobs:read:self','extractions:create:self')"
                        ),
                        {"member": UUID(int=1)},
                    )
                    == 2
                )
                assert (
                    await session.scalar(
                        text("SELECT count(*) FROM role_permissions WHERE role_id=:rid"),
                        {"rid": rid},
                    )
                    == 0
                )
            migrate(url, "downgrade", "0004_career_discovery")
            async with db.sessions() as session:
                assert await session.scalar(text("SELECT count(*) FROM permissions")) == 15
                assert (
                    await session.scalar(
                        text("SELECT count(*) FROM discovery_scans WHERE id=:sid"), {"sid": sid}
                    )
                    == 1
                )
                for table in ("jobs", "extraction_runs", "extraction_outbox"):
                    assert (
                        await session.scalar(text(f"SELECT to_regclass('public.{table}')")) is None
                    )
            migrate(url, "upgrade", "head")
            migrate(url, "check")
        finally:
            await db.close()
