"""OpenRouter chat-completions client for advisory assessments (fixed host, strict output)."""

import json
from decimal import Decimal, InvalidOperation
from time import perf_counter

import httpx
from pydantic import ValidationError

from app.integrations.ai.prompt import PROMPT_VERSION, SCHEMA, messages
from app.integrations.ai.provider import (
    AIError,
    AIInvalidOutput,
    AIRefused,
    AITimeout,
    AIUnavailable,
    Assessment,
    AssessmentOutcome,
    AssessmentRequest,
    Usage,
)

MAX_RESPONSE_BYTES = 256 * 1024


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _usage(body: dict[str, object], latency_ms: int) -> Usage:
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    assert isinstance(usage, dict)
    cost: Decimal | None = None
    if isinstance(usage.get("cost"), int | float) and not isinstance(usage.get("cost"), bool):
        try:
            cost = Decimal(str(usage["cost"]))
        except InvalidOperation:
            cost = None
    return Usage(
        latency_ms,
        _int(usage.get("prompt_tokens")),
        _int(usage.get("completion_tokens")),
        _int(usage.get("total_tokens")),
        cost,
    )


class ProviderError(AIError):
    """Carries usage so failed calls are still recorded."""

    def __init__(self, error: AIError, usage: Usage) -> None:
        super().__init__(error.code)
        self.status = error.status
        self.usage = usage


class OpenRouterProvider:
    name = "openrouter"
    prompt_version = PROMPT_VERSION
    enabled = True

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float,
        max_output_tokens: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 5.0)),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}", "X-Title": "Career Intelligence"},
        )

    def cache_key(self) -> tuple[str, str, str]:
        return (self.name, self.model, self.prompt_version)

    async def aclose(self) -> None:
        await self.client.aclose()

    async def assess(self, request: AssessmentRequest) -> AssessmentOutcome:
        payload = {
            "model": self.model,
            "messages": messages(request),
            "temperature": 0,
            "max_completion_tokens": self.max_output_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "match_assessment", "strict": True, "schema": SCHEMA},
            },
            "provider": {"require_parameters": True},
        }
        start = perf_counter()
        body: dict[str, object] = {}
        try:
            async with self.client.stream("POST", "/chat/completions", json=payload) as response:
                raw = b""
                async for chunk in response.aiter_bytes():
                    raw += chunk
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise AIUnavailable("response_too_large")
                latency = int((perf_counter() - start) * 1000)
                if response.status_code == 408:
                    raise AITimeout("provider_timeout")
                if response.status_code != 200:
                    raise AIUnavailable(f"provider_http_{response.status_code}")
                try:
                    parsed = json.loads(raw)
                except ValueError:
                    raise AIUnavailable("provider_malformed") from None
                body = parsed if isinstance(parsed, dict) else {}
                assessment = self._assessment(body)
                return AssessmentOutcome(assessment, _usage(body, latency))
        except httpx.TimeoutException:
            raise ProviderError(AITimeout("provider_timeout"), Usage(self._ms(start))) from None
        except httpx.HTTPError:
            raise ProviderError(
                AIUnavailable("provider_unreachable"), Usage(self._ms(start))
            ) from None
        except AIError as error:
            raise ProviderError(error, _usage(body, self._ms(start))) from None

    @staticmethod
    def _ms(start: float) -> int:
        return int((perf_counter() - start) * 1000)

    @staticmethod
    def _assessment(body: dict[str, object]) -> Assessment:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise AIInvalidOutput("no_choice")
        choice = choices[0]
        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
        assert isinstance(message, dict)
        if choice.get("finish_reason") == "content_filter" or message.get("refusal"):
            raise AIRefused("provider_refused")
        content = message.get("content")
        if not isinstance(content, str) or len(content) > 20_000:
            raise AIInvalidOutput("no_content")
        try:
            return Assessment.model_validate_json(content)
        except (ValidationError, ValueError):
            raise AIInvalidOutput("schema_mismatch") from None
