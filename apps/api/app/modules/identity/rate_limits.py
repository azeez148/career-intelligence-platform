import hashlib
import hmac
from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert

from app.core.config import Settings
from app.core.errors import DomainError
from app.db.session import Database
from app.modules.identity.models import AuthRateLimit


class RateLimits:
    def __init__(self, database: Database, config: Settings) -> None:
        self.database = database
        self.config = config

    async def consume(
        self, action: str, subject: str, limit: int, seconds: int, at: datetime
    ) -> str:
        window = int(at.timestamp()) // seconds
        key = hmac.new(
            self.config.rate_limit_secret.get_secret_value().encode(),
            f"{action}:{subject}:{window}".encode(),
            hashlib.sha256,
        ).hexdigest()
        expiry = datetime.fromtimestamp((window + 1) * seconds, tz=at.tzinfo)
        async with self.database.sessions() as session, session.begin():
            expired = (
                select(AuthRateLimit.key)
                .where(AuthRateLimit.expires_at < at - timedelta(seconds=60))
                .limit(100)
                .with_for_update(skip_locked=True)
            )
            await session.execute(delete(AuthRateLimit).where(AuthRateLimit.key.in_(expired)))
            statement = (
                insert(AuthRateLimit)
                .values(key=key, action=action, count=1, expires_at=expiry)
                .on_conflict_do_update(
                    index_elements=[AuthRateLimit.key],
                    set_={"count": AuthRateLimit.count + 1},
                    where=AuthRateLimit.count < limit,
                )
                .returning(AuthRateLimit.count)
            )
            count = (await session.execute(statement)).scalar_one_or_none()
        if count is None:
            raise DomainError(
                429,
                "rate_limited",
                "Too many attempts; try again later",
                {"Retry-After": str(max(1, int((expiry - at).total_seconds())))},
            )
        return key

    async def refund(self, key: str) -> None:
        async with self.database.sessions() as session, session.begin():
            await session.execute(
                update(AuthRateLimit)
                .where(AuthRateLimit.key == key, AuthRateLimit.count > 0)
                .values(count=AuthRateLimit.count - 1)
            )
