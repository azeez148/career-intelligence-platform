from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin

from app.core.urls import source_url
from app.integrations.http import Fetched, FetchError
from app.integrations.robots import RobotsPolicy, origin_url
from app.modules.discovery.ats import platform_for
from app.modules.discovery.html import career_score, parse_document
from app.modules.discovery.sitemaps import parse_sitemap

Fetch = Callable[[str], Awaitable[Fetched]]


@dataclass(frozen=True)
class DiscoveredSource:
    url: str
    kind: str
    platform: str | None
    discovery_method: str
    evidence: list[str]


@dataclass(frozen=True)
class DiscoveryOutcome:
    status: str
    resolved_website_url: str | None
    resolution_confidence: str | None
    resolution_evidence: list[str]
    sources: list[DiscoveredSource]
    failure_code: str | None = None


def content_type(page: Fetched) -> str:
    return page.headers.get("content-type", "").split(";", 1)[0].strip().lower()


class DiscoveryPipeline:
    def __init__(self, fetch: Fetch) -> None:
        self.fetch = fetch
        self.robots = RobotsPolicy(fetch)

    async def allowed(self, url: str) -> bool:
        return await self.robots.allowed(url)

    async def run(self, start_url: str, *, explicit_careers: bool = False) -> DiscoveryOutcome:
        start_url = source_url(start_url)
        if not await self.allowed(start_url):
            return DiscoveryOutcome("unsupported", None, None, [], [], "robots_disallowed")
        page = await self.fetch(start_url)
        if page.status in {429, 502, 503, 504}:
            raise FetchError("remote_temporary", transient=True)
        if page.status < 200 or page.status >= 400:
            return DiscoveryOutcome("unsupported", None, None, [], [], "http_status")
        if content_type(page) not in {"text/html", "application/xhtml+xml", ""}:
            return DiscoveryOutcome("unsupported", None, None, [], [], "unsupported_content")
        canonical, links, _ = parse_document(page.body, page.url)
        website = canonical if not explicit_careers else origin_url(canonical)
        sources: dict[str, DiscoveredSource] = {}
        platform = platform_for(canonical)
        if explicit_careers or platform or career_score(canonical):
            source = DiscoveredSource(
                canonical,
                "ats" if platform else "generic_page",
                platform,
                "explicit" if explicit_careers else "page_signal",
                ["explicit_careers"] if explicit_careers else ["career_url_signal"],
            )
            sources[source.url] = source
        candidates = [(link.url, "homepage_link", ["career_link_signal"]) for link in links[:6]]
        candidates.extend(await self._sitemap_candidates(origin_url(page.url)))
        for candidate_url, method, evidence in candidates[:8]:
            if candidate_url in sources or not await self.allowed(candidate_url):
                continue
            candidate = await self.fetch(candidate_url)
            if candidate.status < 200 or candidate.status >= 400:
                continue
            if content_type(candidate) not in {"text/html", "application/xhtml+xml", ""}:
                continue
            final, _, _ = parse_document(candidate.body, candidate.url)
            platform = platform_for(final, candidate.body.decode("utf-8", errors="replace"))
            sources[final] = DiscoveredSource(
                final,
                "ats" if platform else "generic_page",
                platform,
                method,
                evidence + (["ats_recognized"] if platform else ["career_page_reachable"]),
            )
        if not sources:
            return DiscoveryOutcome(
                "unsupported",
                website,
                "user_supplied",
                ["safe_redirect_chain", "user_supplied_start"],
                [],
                "no_career_source",
            )
        return DiscoveryOutcome(
            "succeeded",
            website,
            "user_supplied",
            ["safe_redirect_chain", "user_supplied_start"],
            list(sources.values()),
        )

    async def _sitemap_candidates(self, origin: str) -> list[tuple[str, str, list[str]]]:
        sitemap_urls = self.robots.sitemaps(origin)
        sitemap_urls.append(urljoin(origin, "sitemap.xml"))
        queue = list(dict.fromkeys(sitemap_urls))[:3]
        seen: set[str] = set()
        candidates: list[tuple[str, str, list[str]]] = []
        while queue and len(seen) < 3:
            sitemap_url = queue.pop(0)
            try:
                sitemap_url = source_url(sitemap_url)
            except ValueError:
                continue
            if sitemap_url in seen or not await self.allowed(sitemap_url):
                continue
            seen.add(sitemap_url)
            page = await self.fetch(sitemap_url)
            if page.status < 200 or page.status >= 300:
                continue
            if content_type(page) not in {
                "application/xml",
                "text/xml",
                "application/rss+xml",
                "",
            }:
                continue
            stored = parse_sitemap(page.body)
            for nested in stored.nested:
                if len(queue) + len(seen) < 3:
                    queue.append(nested)
            for url in stored.urls:
                try:
                    normalized = source_url(url)
                except ValueError:
                    continue
                if career_score(normalized):
                    candidates.append((normalized, "sitemap", ["sitemap_career_signal"]))
                    if len(candidates) >= 6:
                        return candidates
        return candidates
