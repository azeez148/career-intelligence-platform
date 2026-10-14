"""Strategy selection for one career source, in the approved order."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.integrations.http import Fetched, FetchError
from app.modules.extraction.strategies import (
    ExtractionContext,
    SourceRef,
    SourceUnsupported,
    StrategyResult,
    greenhouse,
    lever,
)
from app.modules.jobs.normalize import CONFIDENCE_RANK, NormalizedJob

PageStrategy = Callable[[SourceRef, Fetched, ExtractionContext], Awaitable[StrategyResult]]


@dataclass
class ExtractionOutcome:
    status: str
    strategy: str | None = None
    confidence: str | None = None
    jobs: list[NormalizedJob] = field(default_factory=list)
    complete: bool = False
    failure_code: str | None = None
    escalate: bool = False


def unsupported(code: str) -> ExtractionOutcome:
    return ExtractionOutcome("unsupported", failure_code=code)


def finished(result: StrategyResult) -> ExtractionOutcome:
    confidence = min(
        (job.confidence for job in result.jobs),
        key=CONFIDENCE_RANK.__getitem__,
        default=result.confidence,
    )
    return ExtractionOutcome(
        "succeeded" if result.complete else "partial",
        result.strategy,
        confidence,
        result.jobs,
        result.complete,
    )


async def api_result(source: SourceRef, ctx: ExtractionContext) -> StrategyResult | None:
    if source.platform == "greenhouse":
        token = greenhouse.board_token(source.url)
        return await greenhouse.extract(token, ctx) if token else None
    if source.platform == "lever":
        ref = lever.site_ref(source.url)
        return await lever.extract(ref, ctx) if ref else None
    return None


async def embedded_api_result(document: str, ctx: ExtractionContext) -> StrategyResult | None:
    token = greenhouse.embedded_token(document)
    if token:
        return await greenhouse.extract(token, ctx)
    ref = lever.embedded_site(document)
    if ref:
        return await lever.extract(ref, ctx)
    return None


async def extract(
    source: SourceRef, ctx: ExtractionContext, page_strategy: PageStrategy | None = None
) -> ExtractionOutcome:
    """Run official APIs first, then page strategies. FetchErrors propagate to the worker."""
    try:
        result = await api_result(source, ctx)
        if result is not None:
            return finished(result)
        page = await ctx.get(source.url)
        if page is None:
            return unsupported("robots_disallowed")
        if page.status in {429, 502, 503, 504}:
            raise FetchError("remote_temporary", transient=True)
        if page.status == 404 or page.status == 410:
            return unsupported("source_not_found")
        if not 200 <= page.status < 300:
            return unsupported("http_status")
        document = page.body.decode("utf-8", errors="replace")
        if source.platform in {"greenhouse", "lever"}:
            result = await embedded_api_result(document, ctx)
            if result is not None:
                return finished(result)
        if page_strategy is not None:
            result = await page_strategy(source, page, ctx)
            if result.jobs:
                return finished(result)
            if result.needs_browser:
                return ExtractionOutcome("queued", escalate=True)
        return unsupported("no_jobs_recognized")
    except SourceUnsupported as error:
        return unsupported(error.code)
