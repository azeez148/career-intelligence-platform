import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from app.core.urls import source_url

SIGNALS = ("career", "careers", "job", "jobs", "vacancy", "vacancies", "join-us")


@dataclass(frozen=True)
class Link:
    url: str
    text: str
    score: int


class DocumentParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[tuple[str, str]] = []
        self.canonical: str | None = None
        self.title_parts: list[str] = []
        self._anchor: str | None = None
        self._anchor_text: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "a" and values.get("href"):
            self._anchor = values["href"]
            self._anchor_text = []
        elif tag.lower() == "link" and "canonical" in values.get("rel", "").lower():
            self.canonical = values.get("href") or None
        elif tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._anchor is not None:
            self.links.append((self._anchor, " ".join(self._anchor_text)))
            self._anchor = None
            self._anchor_text = []
        elif tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._anchor is not None:
            self._anchor_text.append(data)
        if self._in_title:
            self.title_parts.append(data)


def career_score(url: str, text: str = "") -> int:
    parsed = urlsplit(url)
    path = re.sub(r"[^a-z0-9]+", "-", parsed.path.casefold())
    words = re.sub(r"[^a-z0-9]+", "-", text.casefold())
    score = 0
    for signal in SIGNALS:
        if f"-{signal}-" in f"-{path}-":
            score += 3
        if f"-{signal}-" in f"-{words}-":
            score += 4
    return score


def parse_document(body: bytes, base_url: str, max_links: int = 500) -> tuple[str, list[Link], str]:
    parser = DocumentParser(base_url)
    parser.feed(body[:2_000_000].decode("utf-8", errors="replace"))
    links: dict[str, Link] = {}
    for href, text in parser.links[:max_links]:
        try:
            url = source_url(urljoin(base_url, href))
        except ValueError:
            continue
        link = Link(url=url, text=" ".join(text.split())[:200], score=career_score(url, text))
        if link.score and (url not in links or links[url].score < link.score):
            links[url] = link
    canonical = base_url
    if parser.canonical:
        try:
            candidate = source_url(urljoin(base_url, parser.canonical))
            if urlsplit(candidate).hostname == urlsplit(base_url).hostname:
                canonical = candidate
        except ValueError:
            pass
    return (
        canonical,
        sorted(links.values(), key=lambda row: (-row.score, row.url)),
        " ".join(" ".join(parser.title_parts).split())[:300],
    )
