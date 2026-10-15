import re
from ipaddress import ip_network
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: SecretStr
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    db_connect_timeout: float = Field(default=2, gt=0, le=30)
    db_ready_timeout: float = Field(default=3, gt=0, le=30)
    db_pool_size: int = Field(default=5, ge=1, le=20)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
            if url.drivername != "postgresql+asyncpg" or not url.host or not url.database:
                raise ValueError
        except Exception:
            raise ValueError(
                "A PostgreSQL asyncpg URL with host and database is required"
            ) from None
        return value


class Settings(DatabaseSettings):
    environment: Literal["development", "production"] = "production"
    jwt_secret: SecretStr
    csrf_secret: SecretStr
    rate_limit_secret: SecretStr
    redis_url: SecretStr
    allowed_origins: list[str]
    trusted_proxy_cidrs: list[str] = []
    jwt_issuer: str = "career-intelligence"
    jwt_audience: str = "career-web"
    access_token_seconds: int = Field(default=600, ge=30, le=3600)
    session_seconds: int = Field(default=604800, ge=600, le=2592000)
    csrf_seconds: int = Field(default=86400, ge=600, le=604800)
    password_workers: int = Field(default=2, ge=1, le=8)
    login_account_limit: int = Field(default=5, ge=1, le=100)
    login_ip_limit: int = Field(default=30, ge=1, le=1000)
    registration_ip_limit: int = Field(default=5, ge=1, le=100)
    refresh_session_limit: int = Field(default=30, ge=1, le=1000)
    scan_user_hour_limit: int = Field(default=10, ge=1, le=1000)
    scan_company_hour_limit: int = Field(default=3, ge=1, le=100)
    discovery_domain_interval_ms: int = Field(default=500, ge=100, le=10000)
    discovery_max_attempts: int = Field(default=4, ge=1, le=10)
    discovery_lease_seconds: int = Field(default=120, ge=30, le=900)
    extraction_user_hour_limit: int = Field(default=20, ge=1, le=1000)
    extraction_source_hour_limit: int = Field(default=5, ge=1, le=100)
    extraction_max_attempts: int = Field(default=3, ge=1, le=10)
    extraction_lease_seconds: int = Field(default=240, ge=60, le=1800)
    extraction_browser_enabled: bool = False
    matching_user_hour_limit: int = Field(default=30, ge=1, le=1000)
    # Optional advisory AI. Off unless explicitly enabled with a key and an operator-chosen model.
    ai_enabled: bool = False
    ai_provider: Literal["openrouter"] = "openrouter"
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    ai_model: str | None = Field(default=None, max_length=200)
    ai_timeout_seconds: float = Field(default=20, gt=0, le=60)
    ai_max_output_tokens: int = Field(default=800, ge=100, le=4000)
    ai_user_daily_limit: int = Field(default=20, ge=1, le=1000)
    # Test stacks only: exact public-looking hostnames mapped to fixture containers. Refused in
    # production; never set in compose.yaml.
    outbound_test_hosts: dict[str, str] = {}

    @field_validator("jwt_secret", "csrf_secret", "rate_limit_secret")
    @classmethod
    def strong_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode()) < 32:
            raise ValueError("Secrets must contain at least 32 bytes of random data")
        return value

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def valid_networks(cls, values: list[str]) -> list[str]:
        for value in values:
            ip_network(value)
        return values

    @field_validator("redis_url")
    @classmethod
    def valid_redis_url(cls, value: SecretStr) -> SecretStr:
        parsed = urlsplit(value.get_secret_value())
        if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
            raise ValueError("A redis:// or rediss:// URL with a hostname is required")
        return value

    @model_validator(mode="after")
    def validate_security(self) -> Self:
        if (
            len(
                {
                    self.jwt_secret.get_secret_value(),
                    self.csrf_secret.get_secret_value(),
                    self.rate_limit_secret.get_secret_value(),
                }
            )
            != 3
        ):
            raise ValueError("Use independent secrets for JWT, CSRF, and rate limits")
        if not self.allowed_origins:
            raise ValueError("At least one exact allowed origin is required")
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
                or "*" in origin
            ):
                raise ValueError("Origins must be exact scheme/host/port values")
            if self.environment == "production" and parsed.scheme != "https":
                raise ValueError("Production requires HTTPS origins")
        if self.ai_enabled and (self.openrouter_api_key is None or not self.ai_model):
            raise ValueError("AI_ENABLED requires OPENROUTER_API_KEY and AI_MODEL")
        if self.environment == "production" and self.openrouter_base_url != (
            "https://openrouter.ai/api/v1"
        ):
            raise ValueError("Production AI traffic must use the official OpenRouter API")
        if self.outbound_test_hosts and self.environment == "production":
            raise ValueError("OUTBOUND_TEST_HOSTS is only allowed in development test stacks")
        for host in self.outbound_test_hosts:
            if host != host.lower() or not re.fullmatch(r"[a-z0-9.-]{1,253}", host):
                raise ValueError("OUTBOUND_TEST_HOSTS keys must be exact lowercase hostnames")
        redis = urlsplit(self.redis_url.get_secret_value())
        if self.environment == "production" and not redis.password:
            raise ValueError("Production Redis requires authentication")
        return self

    @property
    def secure_cookies(self) -> bool:
        return self.environment == "production"

    @property
    def access_cookie(self) -> str:
        return "__Host-access" if self.secure_cookies else "dev-access"

    @property
    def refresh_cookie(self) -> str:
        return "__Host-refresh" if self.secure_cookies else "dev-refresh"
