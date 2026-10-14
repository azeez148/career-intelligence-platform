from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("auth_sessions.id", ondelete="CASCADE"), index=True
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replacement_digest: Mapped[str | None] = mapped_column(String(64))


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    action: Mapped[str] = mapped_column(String(32))
    count: Mapped[int] = mapped_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
