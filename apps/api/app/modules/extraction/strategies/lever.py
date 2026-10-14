"""Lever Postings API: GET /v0/postings/{site}?mode=json&skip=N&limit=N (public, read-only)."""

import html
import json
import re
from typing import Any
from urllib.parse import urlsplit

from app.integrations.http import JSON_ACCEPT, FetchError
from app.modules.extraction.strategies import (
    BUDGET_CODES,
    ExtractionContext,
    SourceUnsupported,
    StrategyResult,
    api_status,
)
from app.modules.jobs.normalize import (
    MAX_LOCATION,
    MAX_SHORT,
    NormalizedJob,
    build,
    employment_type,
    html_to_text,
    plain,
    requirements_from_html,
    timestamp,
    work_mode,
)

PAGE_SIZE = 100
SITE = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")
BOARD_HOSTS = {"jobs.lever.co": "api.lever.co", "jobs.eu.lever.co": "api.eu.lever.co"}
API_HOSTS = set(BOARD_HOSTS.values())
EMBED = re.compile(r"https?://jobs(?:\.eu)?\.lever\.co/[A-Za-z0-9_.-]{1,100}", re.IGNORECASE)


def site_ref(url: str) -> tuple[str, str] | None:
    """Return (api host, site) for a Lever hosted board or postings API URL."""
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    segments = [part for part in parsed.path.split("/") if part]
    if host in BOARD_HOSTS and segments and SITE.match(segments[0]):
        return BOARD_HOSTS[host], segments[0]
    if host in API_HOSTS and len(segments) >= 3 and segments[:2] == ["v0", "postings"]:
        return (host, segments[2]) if SITE.match(segments[2]) else None
    return None


def embedded_site(document: str) -> tuple[str, str] | None:
    for match in EMBED.finditer(document[:500_000]):
        found = site_ref(html.unescape(match.group(0)))
        if found:
            return found
    return None


def combined_html(item: dict[str, Any]) -> str | None:
    parts: list[str] = [item["description"]] if isinstance(item.get("description"), str) else []
    lists = item.get("lists")
    for block in lists if isinstance(lists, list) else []:
        if isinstance(block, dict) and isinstance(block.get("content"), str):
            heading = html.escape(block["text"]) if isinstance(block.get("text"), str) else ""
            parts.append(f"<h3>{heading}</h3><ul>{block['content']}</ul>")
    if isinstance(item.get("additional"), str):
        parts.append(f"<h3></h3>{item['additional']}")  # end any labelled list section
    return "".join(parts) or None


async def extract(ref: tuple[str, str], ctx: ExtractionContext) -> StrategyResult:
    host, site = ref
    result = StrategyResult("ats_api", "high", complete=False)
    for page_number in range(ctx.limits.max_listing_pages):
        url = (
            f"https://{host}/v0/postings/{site}?mode=json"
            f"&skip={page_number * PAGE_SIZE}&limit={PAGE_SIZE}"
        )
        try:
            page = await ctx.get(url, accept=JSON_ACCEPT)
        except FetchError as error:
            if error.code in BUDGET_CODES and result.jobs:
                return result
            raise
        if page is None:
            raise SourceUnsupported("robots_disallowed")
        api_status(page)
        try:
            items = json.loads(page.body)
        except ValueError:
            raise SourceUnsupported("malformed_content") from None
        if not isinstance(items, list):
            raise SourceUnsupported("malformed_content")
        for item in items:
            if len(result.jobs) >= ctx.limits.max_jobs:
                return result
            if isinstance(item, dict):
                job = posting(item)
                if job is not None:
                    result.jobs.append(job)
        if len(items) < PAGE_SIZE:
            result.complete = True
            return result
    return result


def posting(item: dict[str, Any]) -> NormalizedJob | None:
    if not isinstance(item.get("hostedUrl"), str):
        return None
    categories = item["categories"] if isinstance(item.get("categories"), dict) else {}
    content = combined_html(item)
    return build(
        url=item["hostedUrl"],
        title=item.get("text"),
        method="ats_api",
        confidence="high",
        sources=dict.fromkeys(
            (
                "title",
                "canonical_url",
                "source_job_id",
                "location_text",
                "work_mode",
                "employment_type",
                "department",
                "description_text",
                "posted_at",
            ),
            "source",
        )
        | {"requirements_text": "heuristic"},
        source_job_id=plain(item.get("id"), MAX_SHORT),
        location_text=plain(categories.get("location"), MAX_LOCATION),
        work_mode=work_mode(item.get("workplaceType")),
        employment_type=employment_type(categories.get("commitment")),
        department=plain(categories.get("team") or categories.get("department"), MAX_SHORT),
        description_text=html_to_text(content),
        requirements_text=requirements_from_html(content),
        posted_at=timestamp(item.get("createdAt")),
    )
