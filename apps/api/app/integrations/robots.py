from collections.abc import Awaitable, Callable
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from app.integrations.http import Fetched, FetchError

Fetch = Callable[[str], Awaitable[Fetched]]
USER_AGENT = "CareerIntelligenceDiscovery"


def origin_url(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}/"


class RobotsPolicy:
    """Per-run robots.txt cache shared by every outbound strategy."""

    def __init__(self, fetch: Fetch) -> None:
        self.fetch = fetch
        self.parsers: dict[str, RobotFileParser | None] = {}

    async def allowed(self, url: str) -> bool:
        origin = origin_url(url)
        if origin not in self.parsers:
            page = await self.fetch(urljoin(origin, "robots.txt"))
            if page.status in {401, 403}:
                parser = RobotFileParser()
                parser.parse(["User-agent: *", "Disallow: /"])
                self.parsers[origin] = parser
            elif 200 <= page.status < 300:
                parser = RobotFileParser()
                parser.parse(page.body.decode("utf-8", errors="replace").splitlines())
                self.parsers[origin] = parser
            elif page.status in {429, 500, 502, 503, 504}:
                raise FetchError("robots_unavailable", transient=True)
            else:
                self.parsers[origin] = None
        cached = self.parsers[origin]
        return cached is None or cached.can_fetch(USER_AGENT, url)

    def sitemaps(self, origin: str) -> list[str]:
        parser = self.parsers.get(origin)
        return list(parser.site_maps() or []) if parser is not None else []
