from datetime import datetime
from uuid import UUID

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=320)
    password: SecretStr

    @field_validator("email")
    @classmethod
    def canonical_email(cls, value: str) -> str:
        try:
            return str(validate_email(value, check_deliverability=False).normalized).casefold()
        except EmailNotValidError:
            raise ValueError("Enter a valid email address") from None

    @field_validator("password")
    @classmethod
    def valid_password(cls, value: SecretStr) -> SecretStr:
        if not 15 <= len(value.get_secret_value()) <= 128:
            raise ValueError("Passwords must contain 15 to 128 characters")
        return value


class Registration(Credentials):
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("display_name")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Display name cannot be blank")
        return value.strip()


class PublicUser(BaseModel):
    id: UUID
    email: str
    display_name: str
    bio: str
    permissions: list[str]


class LoginResult(BaseModel):
    user: PublicUser
    access_expires_at: datetime


class RefreshResult(BaseModel):
    access_expires_at: datetime


class SessionView(BaseModel):
    id: UUID
    created_at: datetime
    expires_at: datetime
    current: bool


class SessionPage(BaseModel):
    items: list[SessionView]
    next_offset: int | None
