"""Chromium rendering in which every browser request is fulfilled by the safe HTTP boundary.

The browser never opens a network connection itself: page requests are intercepted and either
fulfilled through the caller's policy-enforcing fetch (pinned DNS, redirect validation, robots,
budgets) or aborted. A dead proxy with no loopback bypass makes any request that escapes
interception fail closed. Only Playwright's own types are imported at module load time.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from app.core.urls import source_url
from app.integrations.http import Fetched, FetchError

if TYPE_CHECKING:
    from playwright.async_api import Route, WebSocketRoute

logger = logging.getLogger(__name__)

PolicyFetch = Callable[[str, str | None], Awaitable[Fetched | None]]
ALLOWED_RESOURCES = {"document", "script", "xhr", "fetch", "stylesheet"}
PASSED_HEADERS = {"content-type", "content-language", "cache-control", "last-modified", "etag"}
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "CareerIntelligenceDiscovery/0.1 Chrome/140.0 Safari/537.36"
)
LAUNCH_ARGS = [
    "--proxy-server=http://127.0.0.1:9",
    "--proxy-bypass-list=<-loopback>",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-dev-shm-usage",
    "--disable-domain-reliability",
    "--disable-sync",
    "--metrics-recording-only",
    "--no-default-browser-check",
    "--no-first-run",
    "--no-pings",
    "--disable-features=WebRtcHideLocalIpsWithMdns,Translate,MediaRouter",
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--webrtc-ip-handling-policy=disable_non_proxied_udp",
]


@dataclass(frozen=True)
class BrowserLimits:
    max_requests: int = 80
    navigation_seconds: float = 20.0
    settle_seconds: float = 5.0
    total_seconds: float = 45.0
    max_document_chars: int = 2_000_000


@dataclass
class RenderStats:
    requests: int = 0
    fulfilled: int = 0
    blocked: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Rendered:
    url: str
    html: str
    stats: RenderStats


def same_site(source_host: str, host: str) -> bool:
    """Same host, or a host under the source's parent domain (careers.acme.com ~ acme.com)."""
    if host == source_host:
        return True
    labels = source_host.split(".")
    parent = ".".join(labels[1:]) if len(labels) > 2 else source_host
    return host == parent or host.endswith(f".{parent}")


class InterceptingRenderer:
    def __init__(self, fetch: PolicyFetch, limits: BrowserLimits | None = None) -> None:
        self.fetch = fetch
        self.limits = limits or BrowserLimits()

    async def render(self, url: str) -> Rendered:
        try:
            return await asyncio.wait_for(self._render(url), self.limits.total_seconds)
        except TimeoutError:
            raise FetchError("render_timeout", transient=True) from None

    async def _render(self, url: str) -> Rendered:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import async_playwright

        source_host = urlsplit(url).hostname or ""
        stats = RenderStats()
        # Chromium cannot follow a fulfilled 3xx navigation, so resolve the start document's
        # validated redirect chain first and serve that response once from this cache.
        start = await self.fetch(url, None)
        if start is None:
            raise FetchError("robots_disallowed")
        if not 200 <= start.status < 400:
            raise FetchError("render_failed")
        if not same_site(source_host, urlsplit(start.url).hostname or ""):
            raise FetchError("cross_site_blocked")
        prefetched: dict[str, Fetched] = {start.url: start}
        stats.requests += 1

        async def handle(route: "Route") -> None:
            request = route.request
            target = request.url
            reason = self._rejection(request.method, request.resource_type, target, source_host)
            if reason is None and stats.requests >= self.limits.max_requests:
                reason = "browser_budget_exceeded"
            if reason is not None:
                stats.blocked.append(reason)
                await route.abort("blockedbyclient")
                return
            cached = prefetched.pop(target, None)
            if cached is not None:
                page: Fetched | None = cached
            else:
                stats.requests += 1
                try:
                    page = await self.fetch(target, request.headers.get("accept"))
                except FetchError as error:
                    stats.blocked.append(error.code)
                    await route.abort("failed")
                    return
            if page is None:
                stats.blocked.append("robots_disallowed")
                await route.abort("blockedbyclient")
                return
            # A redirected subresource is served at its requested URL with the final body.
            headers = {key: value for key, value in page.headers.items() if key in PASSED_HEADERS}
            stats.fulfilled += 1
            await route.fulfill(status=page.status, headers=headers, body=page.body)

        async def close_socket(socket: "WebSocketRoute") -> None:
            stats.blocked.append("websocket_blocked")
            await socket.close(code=1008, reason="blocked")

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, args=LAUNCH_ARGS)
            try:
                context = await browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1280, "height": 900},
                    service_workers="block",
                    accept_downloads=False,
                    java_script_enabled=True,
                    ignore_https_errors=False,
                    permissions=[],
                )
                await context.route("**/*", handle)
                await context.route_web_socket("**/*", close_socket)
                page = await context.new_page()
                page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.dismiss()))
                page.on("popup", lambda popup: asyncio.ensure_future(popup.close()))
                try:
                    response = await page.goto(
                        start.url,
                        wait_until="domcontentloaded",
                        timeout=self.limits.navigation_seconds * 1000,
                    )
                except PlaywrightError:
                    raise FetchError("render_failed") from None
                if response is None or not 200 <= response.status < 400:
                    raise FetchError("render_failed")
                try:
                    await page.wait_for_load_state(
                        "networkidle", timeout=self.limits.settle_seconds * 1000
                    )
                except PlaywrightError:
                    pass  # Long-polling pages never idle; render what has settled.
                html = (await page.content())[: self.limits.max_document_chars]
                return Rendered(page.url, html, stats)
            finally:
                await browser.close()

    @staticmethod
    def _rejection(method: str, resource_type: str, url: str, source_host: str) -> str | None:
        if method != "GET":
            return "method_blocked"
        if resource_type not in ALLOWED_RESOURCES:
            return "resource_blocked"
        try:
            normalized = source_url(url.split("#", 1)[0])
        except ValueError:
            return "url_blocked"
        if not same_site(source_host, urlsplit(normalized).hostname or ""):
            return "cross_site_blocked"
        return None
