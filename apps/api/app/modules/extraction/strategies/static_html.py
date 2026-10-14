"""Page strategies: JSON-LD JobPosting data first, then generic repeated job-link listings."""

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from app.integrations.http import Fetched, FetchError
from app.modules.extraction.strategies import (
    BUDGET_CODES,
    ExtractionContext,
    SourceRef,
    StrategyResult,
)
from app.modules.extraction.strategies.structured_data import postings, to_job
from app.modules.jobs.normalize import (
    MAX_TITLE,
    NormalizedJob,
    build,
    canonical_job_url,
    html_to_text,
    plain,
    requirements_from_html,
)

HTML_TYPES = {"text/html", "application/xhtml+xml", ""}
JOB_PATH = re.compile(
    r"(?:^|[/_-])(jobs?|careers?|positions?|openings?|vacanc(?:y|ies)|roles?|postings?|"
    r"opportunit(?:y|ies)|requisitions?)(?:$|[/_-])",
    re.I,
)
SLUG = re.compile(r"(?=.*[a-z0-9])[a-z0-9][a-z0-9._~%-]*\Z", re.I)
LAYOUT = {"nav", "header", "footer", "aside", "form"}
MIN_GROUP = 3
MIN_VISIBLE_TEXT = 200


@dataclass
class PageInfo:
    anchors: list[tuple[str, str, str]] = field(default_factory=list)  # href, text, rel
    next_links: list[str] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    scripts: int = 0
    visible_text: int = 0


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.info = PageInfo()
        self._anchor: tuple[str, str] | None = None
        self._text: list[str] = []
        self._h1: list[str] | None = None
        self._hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = {key.lower(): value or "" for key, value in attrs}
        rel = values.get("rel", "").lower()
        if tag == "script":
            self.info.scripts += 1
        if tag in {"script", "style", "noscript", "template"}:
            self._hidden += 1
        elif tag == "link" and "next" in rel.split() and values.get("href"):
            self.info.next_links.append(values["href"])
        elif tag == "a" and values.get("href") and len(self.info.anchors) < 2000:
            self._anchor = (values["href"], rel)
            self._text = []
        elif tag == "h1":
            self._h1 = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "template"}:
            self._hidden = max(self._hidden - 1, 0)
        elif tag == "a" and self._anchor is not None:
            href, rel = self._anchor
            text = " ".join("".join(self._text).split())[:300]
            self.info.anchors.append((href, text, rel))
            if "next" in rel.split():
                self.info.next_links.append(href)
            self._anchor = None
        elif tag == "h1" and self._h1 is not None:
            self.info.headings.append(" ".join("".join(self._h1).split()))
            self._h1 = None

    def handle_data(self, data: str) -> None:
        if self._hidden:
            return
        self.info.visible_text += len(data.strip())
        if self._anchor is not None:
            self._text.append(data)
        if self._h1 is not None:
            self._h1.append(data)


def parse_page(document: str) -> PageInfo:
    parser = _PageParser()
    parser.feed(document[:2_000_000])
    parser.close()
    return parser.info


def _resolve(base: str, href: str) -> str | None:
    try:
        url = urljoin(base, href.strip())
        return canonical_job_url(url) if urlsplit(url).scheme in {"http", "https"} else None
    except ValueError:
        return None


def job_candidates(page_url: str, info: PageInfo) -> list[tuple[str, str, str]]:
    """Same-host job-like links on one page as (group key, url, anchor text)."""
    host = urlsplit(page_url).hostname
    page_path = urlsplit(page_url).path.rstrip("/")
    found: list[tuple[str, str, str]] = []
    for href, text, _ in info.anchors:
        url = _resolve(page_url, href)
        if url is None:
            continue
        parsed = urlsplit(url)
        segments = [part for part in parsed.path.split("/") if part]
        if parsed.hostname != host or not segments or parsed.path.rstrip("/") == page_path:
            continue
        leaf, parent = segments[-1], "/".join(segments[:-1])
        if not SLUG.match(leaf) or not JOB_PATH.search(f"/{parent}/"):
            continue
        if not re.search(r"\d|-", leaf) and not parsed.query:
            continue  # Single words such as /jobs/search are navigation, not postings.
        found.append((parent, url, text))
    return found


def job_links(candidates: list[tuple[str, str, str]]) -> list[tuple[str, str]]:
    """The largest group of repeated job-like links across all listing pages."""
    groups: dict[str, dict[str, str]] = {}
    for parent, url, text in candidates:
        groups.setdefault(parent, {}).setdefault(url, text)
    qualifying = [links for links in groups.values() if len(links) >= MIN_GROUP]
    return list(max(qualifying, key=len).items()) if qualifying else []


def next_page(page_url: str, info: PageInfo, page_number: int, visited: set[str]) -> str | None:
    host = urlsplit(page_url).hostname
    candidates = list(info.next_links)
    candidates += [href for href, text, _ in info.anchors if text == str(page_number + 1)]
    for href in candidates:
        url = _resolve(page_url, href)
        if url and urlsplit(url).hostname == host and url not in visited:
            return url
    return None


def needs_browser(info: PageInfo) -> bool:
    return info.scripts > 0 and info.visible_text < MIN_VISIBLE_TEXT


def heuristic_job(
    url: str, title: str, document: str | None, method: str = "static_html"
) -> NormalizedJob | None:
    description = requirements = None
    if document is not None:
        info = parse_page(document)
        title = next((heading for heading in info.headings if heading), title)
        content = _without_layout(document)
        description = html_to_text(content)
        requirements = requirements_from_html(content)
    return build(
        url=url,
        title=plain(title, MAX_TITLE),
        method=method,
        confidence="low",
        sources=dict.fromkeys(("title", "description_text", "requirements_text"), "heuristic")
        | {"canonical_url": "page"},
        description_text=description,
        requirements_text=requirements,
    )


def _without_layout(document: str) -> str:
    pattern = "|".join(LAYOUT)
    return re.sub(rf"<({pattern})\b.*?</\1\s*>", " ", document[:2_000_000], flags=re.I | re.S)


def is_html(page: Fetched) -> bool:
    return page.headers.get("content-type", "").split(";", 1)[0].strip().lower() in HTML_TYPES


async def extract(source: SourceRef, first: Fetched, ctx: ExtractionContext) -> StrategyResult:
    """Static strategy over the already-fetched source page, bounded by context limits."""
    limits = ctx.limits
    if not is_html(first):
        return StrategyResult("static_html", "low")
    document = first.body.decode("utf-8", errors="replace")
    structured = [job for node in postings(document) if (job := to_job(node, first.url))]
    if structured:
        return StrategyResult("structured_data", "medium", structured[: limits.max_jobs])
    info = parse_page(document)
    candidates: list[tuple[str, str, str]] = []
    complete = True
    visited = {first.url}
    page_url, page_info = first.url, info
    for page_number in range(1, limits.max_listing_pages + 1):
        candidates += job_candidates(page_url, page_info)
        following = next_page(page_url, page_info, page_number, visited)
        if following is None:
            break
        if page_number == limits.max_listing_pages:
            complete = False
            break
        visited.add(following)
        try:
            page = await ctx.get(following)
        except FetchError as error:
            if error.code not in BUDGET_CODES:
                raise
            complete = False
            break
        if page is None or not 200 <= page.status < 300 or not is_html(page):
            complete = False
            break
        page_url, page_info = page.url, parse_page(page.body.decode("utf-8", errors="replace"))
    links = dict(job_links(candidates))
    if not links:
        return StrategyResult("static_html", "low", needs_browser=needs_browser(info))
    if len(links) > limits.max_jobs:
        complete = False
    jobs: list[NormalizedJob] = []
    method = "static_html"
    for index, (url, text) in enumerate(list(links.items())[: limits.max_jobs]):
        detail: Fetched | None = None
        if index < limits.max_detail_pages:
            try:
                detail = await ctx.get(url)
            except FetchError as error:
                if error.code not in BUDGET_CODES and not error.transient:
                    raise
        body = None
        if detail is not None and 200 <= detail.status < 300 and is_html(detail):
            body = detail.body.decode("utf-8", errors="replace")
            nodes = postings(body)
            if nodes and (job := to_job(nodes[0], url)):
                job.shared_url = False  # A detail page URL is the posting's own URL.
                jobs.append(job)
                method = "structured_data"
                continue
        job = heuristic_job(url, text, body)
        if job is not None:
            jobs.append(job)
    strategy = "static_html" if any(job.confidence == "low" for job in jobs) else method
    return StrategyResult(strategy, "low", jobs, complete)
