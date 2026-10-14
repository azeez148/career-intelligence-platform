"""Extraction strategies. Each one receives fetched documents only through `ExtractionContext`."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.integrations.http import Fetched, FetchError
from app.integrations.robots import RobotsPolicy
from app.modules.jobs.normalize import NormalizedJob

Fetch = Callable[..., Awaitable[Fetched]]
BUDGET_CODES = {"response_budget_exceeded", "scan_budget_exceeded"}


class SourceUnsupported(Exception):
    """The source cannot be extracted; `code` is a safe, user-visible reason."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ExtractionLimits:
    max_listing_pages: int = 10
    max_detail_pages: int = 40
    max_jobs: int = 1000


@dataclass(frozen=True)
class SourceRef:
    url: str
    platform: str | None


@dataclass
class StrategyResult:
    strategy: str
    confidence: str
    jobs: list[NormalizedJob] = field(default_factory=list)
    complete: bool = True
    needs_browser: bool = False


class ExtractionContext:
    def __init__(
        self,
        fetch: Fetch,
        limits: ExtractionLimits | None = None,
        robots: RobotsPolicy | None = None,
    ) -> None:
        self.fetch = fetch
        self.limits = limits or ExtractionLimits()
        self.robots = robots or RobotsPolicy(fetch)

    async def get(self, url: str, *, accept: str | None = None) -> Fetched | None:
        """Fetch when robots allow it; None means robots disallow the URL."""
        if not await self.robots.allowed(url):
            return None
        if accept is None:
            return await self.fetch(url)
        return await self.fetch(url, accept=accept)


def api_status(page: Fetched) -> None:
    """Map public API HTTP status codes to safe outcomes."""
    if page.status == 404:
        raise SourceUnsupported("source_not_found")
    if page.status in {429, 500, 502, 503, 504}:
        raise FetchError("api_unavailable", transient=True)
    if page.status != 200:
        raise SourceUnsupported("api_unavailable")
