from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from test_postgres import POSTGRES_IMAGE, migrate
from testcontainers.community.postgres import PostgresContainer

from app.core.config import Settings
from app.db.session import Database

pytestmark = pytest.mark.integration


async def test_phase3_upgrade_preserves_phase2_and_custom_roles_then_downgrades():
    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as container:
        url = container.get_connection_url()
        migrate(url, "upgrade", "0003_companies_preferences")
        db = Database(Settings(database_url=SecretStr(url)))
        uid, rid, cid = UUID(int=300), UUID(int=301), UUID(int=302)
        try:
            async with db.sessions() as session, session.begin():
                await session.execute(
                    text(
                        "INSERT INTO users(id,email,password_hash,active) "
                        "VALUES (:id,'phase3@example.com','fixture-hash',true)"
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
                        "INSERT INTO roles(id,code,description,default_registration) "
                        "VALUES (:id,'phase3-custom','Custom',false)"
                    ),
                    {"id": rid},
                )
                await session.execute(
                    text(
                        "INSERT INTO role_permissions(role_id,permission_id) "
                        "VALUES (:id,:permission)"
                    ),
                    {"id": rid, "permission": UUID(int=2)},
                )
            migrate(url, "upgrade", "0004_career_discovery")
            migrate(url, "upgrade", "0004_career_discovery")
            async with db.sessions() as session:
                assert await session.scalar(text("SELECT count(*) FROM permissions")) == 15
                assert (
                    await session.scalar(
                        text("SELECT count(*) FROM companies WHERE id=:cid"), {"cid": cid}
                    )
                    == 1
                )
                assert (
                    await session.scalar(
                        text("SELECT count(*) FROM role_permissions WHERE role_id=:rid"),
                        {"rid": rid},
                    )
                    == 1
                )
            migrate(url, "downgrade", "0003_companies_preferences")
            async with db.sessions() as session:
                assert await session.scalar(text("SELECT count(*) FROM permissions")) == 12
                assert (
                    await session.scalar(
                        text("SELECT count(*) FROM companies WHERE id=:cid"), {"cid": cid}
                    )
                    == 1
                )
                assert (
                    await session.scalar(text("SELECT to_regclass('public.discovery_scans')"))
                    is None
                )
            migrate(url, "upgrade", "head")
            migrate(url, "check")
        finally:
            await db.close()
