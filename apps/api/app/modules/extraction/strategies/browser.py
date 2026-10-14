"""Browser-rendered extraction for pages whose job listings only exist after JavaScript runs."""

from app.integrations.browser import BrowserLimits, InterceptingRenderer
from app.integrations.http import Fetched, FetchError
from app.modules.extraction.strategies import (
    BUDGET_CODES,
    ExtractionContext,
    SourceRef,
    StrategyResult,
)
from app.modules.extraction.strategies.static_html import (
    heuristic_job,
    job_candidates,
    job_links,
    next_page,
    parse_page,
)
from app.modules.extraction.strategies.structured_data import postings, to_job
from app.modules.jobs.normalize import NormalizedJob

LISTING_LIMITS = BrowserLimits()
DETAIL_LIMITS = BrowserLimits(total_seconds=30.0, navigation_seconds=15.0, settle_seconds=3.0)
MAX_DETAIL_RENDERS = 3


def renderer(ctx: ExtractionContext, limits: BrowserLimits) -> InterceptingRenderer:
    async def policy_fetch(url: str, accept: str | None) -> Fetched | None:
        return await ctx.get(url, accept=accept)

    return InterceptingRenderer(policy_fetch, limits)


async def extract(source: SourceRef, first: Fetched, ctx: ExtractionContext) -> StrategyResult:
    rendered = await renderer(ctx, LISTING_LIMITS).render(source.url)
    nodes = postings(rendered.html)
    structured = [job for node in nodes if (job := to_job(node, rendered.url, "browser"))]
    if structured:
        return StrategyResult("browser", "medium", structured[: ctx.limits.max_jobs])
    info = parse_page(rendered.html)
    links = job_links(job_candidates(rendered.url, info))
    # Listings paginated by script controls cannot be proven complete without clicking.
    complete = next_page(rendered.url, info, 1, {rendered.url}) is None
    if len(links) > ctx.limits.max_jobs:
        complete = False
    jobs: list[NormalizedJob] = []
    for index, (url, text) in enumerate(links[: ctx.limits.max_jobs]):
        document = None
        if index < MAX_DETAIL_RENDERS:
            try:
                document = (await renderer(ctx, DETAIL_LIMITS).render(url)).html
            except FetchError as error:
                if not error.transient and error.code not in BUDGET_CODES | {"render_failed"}:
                    raise
        if document is not None:
            detail = postings(document)
            if detail and (job := to_job(detail[0], url, "browser")):
                job.shared_url = False  # A detail page URL is the posting's own URL.
                jobs.append(job)
                continue
        job = heuristic_job(url, text, document, method="browser")
        if job is not None:
            jobs.append(job)
    return StrategyResult("browser", "low", jobs, complete)
