"""Provider-independent AI boundary. Domain code depends only on this module."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field


class AIError(Exception):
    """A safe, user-visible failure category recorded in usage."""

    status = "unavailable"

    def __init__(self, code: str = "provider_unavailable") -> None:
        self.code = code
        super().__init__(code)


class AIUnavailable(AIError):
    status = "unavailable"


class AITimeout(AIError):
    status = "timeout"


class AIInvalidOutput(AIError):
    status = "invalid_output"


class AIRefused(AIError):
    status = "refused"


class Assessment(BaseModel):
    """The only shape accepted from a provider; anything else is invalid output."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    summary: str = Field(min_length=1, max_length=600)
    requirements: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(
        default_factory=list, max_length=20
    )
    notes: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        default_factory=list, max_length=10
    )


@dataclass(frozen=True)
class AssessmentRequest:
    title: str
    location_text: str | None
    work_mode: str
    employment_type: str
    description_text: str | None
    requirements_text: str | None
    criteria: dict[str, object]


@dataclass(frozen=True)
class Usage:
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost: Decimal | None = None


@dataclass
class AssessmentOutcome:
    assessment: Assessment
    usage: Usage = field(default_factory=lambda: Usage(0))


class AIProvider(Protocol):
    name: str
    model: str
    prompt_version: str
    enabled: bool

    def cache_key(self) -> tuple[str, str, str]: ...

    async def assess(self, request: AssessmentRequest) -> AssessmentOutcome:
        """Return a validated assessment or raise an `AIError` subclass (with usage attached)."""
        ...


class DisabledProvider:
    name = "disabled"
    model = "none"
    prompt_version = "none"
    enabled = False

    def cache_key(self) -> tuple[str, str, str]:
        return (self.name, self.model, self.prompt_version)

    async def assess(self, request: AssessmentRequest) -> AssessmentOutcome:
        raise AIUnavailable("ai_disabled")
