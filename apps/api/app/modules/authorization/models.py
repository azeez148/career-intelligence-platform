from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        Index(
            "uq_roles_default",
            "default_registration",
            unique=True,
            postgresql_where=text("default_registration = true"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(String(255))
    default_registration: Mapped[bool] = mapped_column(default=False)


class Permission(Base):
    __tablename__ = "permissions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(String(255))


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[UUID] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )
