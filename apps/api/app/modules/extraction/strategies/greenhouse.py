"""Greenhouse Job Board API: GET /v1/boards/{token}/jobs?content=true (public, read-only)."""

import html
import json
import re
from urllib.parse import parse_qs, urlsplit

from app.integrations.http import JSON_ACCEPT
from app.modules.extraction.strategies import (
    ExtractionContext,
    SourceUnsupported,
    StrategyResult,
    api_status,
)
from app.modules.jobs.normalize import (
    MAX_LOCATION,
    MAX_SHORT,
    build,
    html_to_text,
    plain,
    requirements_from_html,
    timestamp,
    work_mode,
)

BOARD_HOSTS = {"boards.greenhouse.io", "job-boards.greenhouse.io"}
API_HOST = "boards-api.greenhouse.io"
TOKEN = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")
EMBED = re.compile(
    r"https?://(?:boards|job-boards)\.greenhouse\.io/[A-Za-z0-9_/?=&.-]{1,300}", re.IGNORECASE
)


def board_token(url: str) -> str | None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    segments = [part for part in parsed.path.split("/") if part]
    token: str | None = None
    if host == API_HOST and len(segments) >= 3 and segments[:2] == ["v1", "boards"]:
        token = segments[2]
    elif host in BOARD_HOSTS and segments:
        if segments[0] == "embed":
            values = parse_qs(parsed.query).get("for")
            token = values[0] if values else None
        else:
            token = segments[0]
    return token if token and TOKEN.match(token) else None


def embedded_token(document: str) -> str | None:
    for match in EMBED.finditer(document[:500_000]):
        token = board_token(html.unescape(match.group(0)))
        if token:
            return token
    return None


async def extract(token: str, ctx: ExtractionContext) -> StrategyResult:
    url = f"https://{API_HOST}/v1/boards/{token}/jobs?content=true"
    page = await ctx.get(url, accept=JSON_ACCEPT)
    if page is None:
        raise SourceUnsupported("robots_disallowed")
    api_status(page)
    try:
        data = json.loads(page.body)
    except ValueError:
        raise SourceUnsupported("malformed_content") from None
    items = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise SourceUnsupported("malformed_content")
    result = StrategyResult("ats_api", "high", complete=len(items) <= ctx.limits.max_jobs)
    for item in items[: ctx.limits.max_jobs]:
        if not isinstance(item, dict) or not isinstance(item.get("absolute_url"), str):
            continue
        content = html.unescape(item["content"]) if isinstance(item.get("content"), str) else None
        location = item.get("location")
        location_text = (
            plain(location.get("name"), MAX_LOCATION) if isinstance(location, dict) else None
        )
        departments = [
            row["name"]
            for row in item.get("departments") or []
            if isinstance(row, dict) and isinstance(row.get("name"), str)
        ]
        job = build(
            url=item["absolute_url"],
            title=item.get("title"),
            method="ats_api",
            confidence="high",
            sources=dict.fromkeys(
                (
                    "title",
                    "canonical_url",
                    "source_job_id",
                    "location_text",
                    "work_mode",
                    "department",
                    "description_text",
                    "posted_at",
                ),
                "source",
            )
            | {"requirements_text": "heuristic"},
            source_job_id=str(item["id"]) if isinstance(item.get("id"), int | str) else None,
            location_text=location_text,
            work_mode=work_mode(location_text),
            department=plain(", ".join(departments), MAX_SHORT),
            description_text=html_to_text(content),
            requirements_text=requirements_from_html(content),
            posted_at=timestamp(item.get("first_published")),
        )
        if job is not None:
            result.jobs.append(job)
    return result
