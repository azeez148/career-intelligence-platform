from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from test_postgres import POSTGRES_IMAGE, migrate
from testcontainers.community.postgres import PostgresContainer

from app.core.config import Settings
from app.db.session import Database

pytestmark = pytest.mark.integration


async def test_upgrade_preserves_accounts_and_custom_rbac_then_downgrades():
    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as container:
        url = container.get_connection_url()
        migrate(url, "upgrade", "0002_identity_profiles_rbac")
        db = Database(Settings(database_url=SecretStr(url)))
        uid, sid, rid = UUID(int=200), UUID(int=201), UUID(int=202)
        try:
            async with db.sessions() as session, session.begin():
                await session.execute(
                    text(
                        "INSERT INTO users(id,email,password_hash,active) "
                        "VALUES (:id,'preserved@example.com','fixture-hash',true)"
                    ),
                    {"id": uid},
                )
                await session.execute(
                    text(
                        "INSERT INTO user_profiles(user_id,display_name,bio) "
                        "VALUES (:id,'Preserved','Original bio')"
                    ),
                    {"id": uid},
                )
                await session.execute(
                    text(
                        "INSERT INTO auth_sessions(id,user_id,created_at,expires_at) "
                        "VALUES (:sid,:uid,now(),now()+interval '7 days')"
                    ),
                    {"sid": sid, "uid": uid},
                )
                await session.execute(
                    text(
                        "INSERT INTO roles(id,code,description,default_registration) "
                        "VALUES (:id,'custom','Custom role',false)"
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
                await session.execute(
                    text("INSERT INTO user_roles(user_id,role_id) VALUES (:uid,:rid)"),
                    {"uid": uid, "rid": rid},
                )
            migrate(url, "upgrade", "0003_companies_preferences")
            migrate(url, "upgrade", "0003_companies_preferences")
            async with db.sessions() as session:
                assert await session.scalar(text("SELECT count(*) FROM permissions")) == 12
                assert (
                    await session.scalar(
                        text("SELECT count(*) FROM role_permissions WHERE role_id=:rid"),
                        {"rid": rid},
                    )
                    == 1
                )
                assert (
                    await session.scalar(
                        text("SELECT display_name FROM user_profiles WHERE user_id=:uid"),
                        {"uid": uid},
                    )
                    == "Preserved"
                )
                assert (
                    await session.scalar(
                        text("SELECT count(*) FROM auth_sessions WHERE id=:sid"), {"sid": sid}
                    )
                    == 1
                )
            migrate(url, "downgrade", "0002_identity_profiles_rbac")
            async with db.sessions() as session:
                assert await session.scalar(text("SELECT count(*) FROM permissions")) == 4
                assert (
                    await session.scalar(
                        text("SELECT count(*) FROM users WHERE id=:uid"), {"uid": uid}
                    )
                    == 1
                )
                assert (
                    await session.scalar(
                        text("SELECT count(*) FROM user_roles WHERE user_id=:uid"), {"uid": uid}
                    )
                    == 1
                )
                assert await session.scalar(text("SELECT to_regclass('public.companies')")) is None
            migrate(url, "upgrade", "0003_companies_preferences")
        finally:
            await db.close()
