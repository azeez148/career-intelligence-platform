from pathlib import Path

from app.integrations.http import Fetched, FetchError

FIXTURES = Path(__file__).parent / "fixtures" / "extraction"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class FakeWeb:
    """In-memory responses keyed by exact URL. Unknown robots.txt is a 404 (allow all)."""

    def __init__(self, pages: dict[str, tuple[int, str, bytes] | FetchError]) -> None:
        self.pages = pages
        self.requests: list[tuple[str, str | None]] = []

    async def fetch(self, url: str, *, accept: str | None = None) -> Fetched:
        self.requests.append((url, accept))
        page = self.pages.get(url)
        if isinstance(page, FetchError):
            raise page
        if page is None:
            return Fetched(url, 404, {"content-type": "text/plain"}, b"")
        status, content_type, body = page
        return Fetched(url, status, {"content-type": content_type}, body)

    def fetched(self) -> list[str]:
        return [url for url, _ in self.requests if not url.endswith("/robots.txt")]


def html(body: str) -> tuple[int, str, bytes]:
    return 200, "text/html; charset=utf-8", body.encode()


def json_page(body: bytes) -> tuple[int, str, bytes]:
    return 200, "application/json", body
