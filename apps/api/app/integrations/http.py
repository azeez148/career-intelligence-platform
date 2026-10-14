import asyncio
import socket
import ssl
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable, Iterable
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Self, cast
from urllib.parse import urljoin, urlsplit

import anyio
import httpcore
import httpx
from httpcore._backends.anyio import AnyIOBackend
from httpcore._backends.base import SOCKET_OPTION

from app.core.urls import source_url

Resolver = Callable[[str, int], Awaitable[list[str]]]
Connector = Callable[
    [str, int, float | None, str | None, Iterable[SOCKET_OPTION] | None],
    Awaitable[httpcore.AsyncNetworkStream],
]
RateLimit = Callable[[str], Awaitable[None]]


class FetchError(Exception):
    def __init__(
        self, code: str, *, transient: bool = False, retry_after: float | None = None
    ) -> None:
        self.code = code
        self.transient = transient
        self.retry_after = retry_after
        super().__init__(code)


async def resolve_host(host: str, port: int) -> list[str]:
    records = await asyncio.get_running_loop().getaddrinfo(
        host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
    )
    return list(dict.fromkeys(record[4][0] for record in records))


async def connect_ip(
    host: str,
    port: int,
    timeout: float | None,  # noqa: ASYNC109 -- required by httpcore
    local_address: str | None,
    socket_options: Iterable[SOCKET_OPTION] | None,
) -> httpcore.AsyncNetworkStream:
    return await AnyIOBackend().connect_tcp(
        host, port, timeout=timeout, local_address=local_address, socket_options=socket_options
    )


def public_addresses(addresses: list[str]) -> list[str]:
    if not addresses:
        raise FetchError("dns_unavailable", transient=True)
    parsed = []
    for value in addresses:
        try:
            address = ip_address(value)
        except ValueError:
            raise FetchError("dns_invalid") from None
        if not address.is_global:
            raise FetchError("dns_blocked")
        parsed.append(address.compressed)
    return list(dict.fromkeys(parsed))


class PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(
        self, resolver: Resolver = resolve_host, connector: Connector = connect_ip
    ) -> None:
        self.resolver = resolver
        self.connector = connector

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 -- required by httpcore
        local_address: str | None = None,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            ip_address(host)
        except ValueError:
            pass
        else:
            raise FetchError("dns_blocked")
        try:
            addresses = public_addresses(await self.resolver(host, port))
        except FetchError:
            raise
        except (OSError, UnicodeError):
            raise FetchError("dns_unavailable", transient=True) from None
        last_error: Exception | None = None
        for address in addresses:
            try:
                stream = await self.connector(address, port, timeout, local_address, socket_options)
                peer = stream.get_extra_info("server_addr")
                if not isinstance(peer, tuple) or not peer:
                    await stream.aclose()
                    raise FetchError("peer_unverified")
                if ip_address(str(peer[0])) != ip_address(address):
                    await stream.aclose()
                    raise FetchError("peer_mismatch")
                return stream
            except FetchError:
                raise
            except Exception as error:
                last_error = error
        raise FetchError("connect_failed", transient=True) from last_error

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 -- required by httpcore
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise FetchError("unix_socket_blocked")

    async def sleep(self, seconds: float) -> None:
        await anyio.sleep(seconds)


class CoreResponseStream(httpx.AsyncByteStream):
    def __init__(self, stream: AsyncIterable[bytes]) -> None:
        self.stream = stream

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self.stream:
            yield chunk

    async def aclose(self) -> None:
        close = getattr(self.stream, "aclose", None)
        if close is not None:
            await close()


class PinnedTransport(httpx.AsyncBaseTransport):
    def __init__(self, backend: PinnedNetworkBackend | None = None) -> None:
        self.pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl.create_default_context(),
            max_connections=4,
            max_keepalive_connections=0,
            http1=True,
            http2=False,
            retries=0,
            network_backend=backend or PinnedNetworkBackend(),
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        assert isinstance(request.stream, httpx.AsyncByteStream)
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        try:
            response = await self.pool.handle_async_request(core_request)
        except FetchError:
            raise
        except httpcore.TimeoutException:
            raise FetchError("timeout", transient=True) from None
        except httpcore.NetworkError:
            raise FetchError("connect_failed", transient=True) from None
        return httpx.Response(
            status_code=response.status,
            headers=response.headers,
            stream=CoreResponseStream(cast(AsyncIterable[bytes], response.stream)),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self.pool.aclose()


@dataclass(frozen=True)
class FetchLimits:
    max_responses: int = 12
    max_redirects: int = 5
    max_response_bytes: int = 2 * 1024 * 1024
    max_total_bytes: int = 10 * 1024 * 1024
    connect_timeout: float = 5.0
    read_timeout: float = 10.0


DEFAULT_FETCH_LIMITS = FetchLimits()


@dataclass(frozen=True)
class Fetched:
    url: str
    status: int
    headers: dict[str, str]
    body: bytes


class SafeHttpClient:
    def __init__(
        self,
        *,
        limits: FetchLimits = DEFAULT_FETCH_LIMITS,
        transport: httpx.AsyncBaseTransport | None = None,
        rate_limit: RateLimit | None = None,
    ) -> None:
        self.limits = limits
        self.responses = 0
        self.total_bytes = 0
        self.rate_limit = rate_limit
        self.client = httpx.AsyncClient(
            transport=transport or PinnedTransport(),
            timeout=httpx.Timeout(
                limits.read_timeout,
                connect=limits.connect_timeout,
                pool=limits.connect_timeout,
                write=limits.read_timeout,
            ),
            follow_redirects=False,
            trust_env=False,
            headers={
                "User-Agent": "CareerIntelligenceDiscovery/0.1 (+local-operator)",
                "Accept": "text/html,application/xhtml+xml,application/xml,text/plain;q=0.8",
            },
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self.client.aclose()

    async def fetch(self, url: str) -> Fetched:
        current = self._safe_url(url, "url_invalid")
        visited: set[str] = set()
        for _ in range(self.limits.max_redirects + 1):
            if current in visited:
                raise FetchError("redirect_loop")
            visited.add(current)
            if self.responses >= self.limits.max_responses:
                raise FetchError("response_budget_exceeded")
            host = urlsplit(current).hostname or ""
            if self.rate_limit is not None:
                await self.rate_limit(host)
            try:
                async with self.client.stream("GET", current) as response:
                    self.responses += 1
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError("redirect_invalid")
                        current = self._safe_url(urljoin(current, location), "redirect_invalid")
                        continue
                    body = await self._body(response)
                    return Fetched(
                        url=str(response.url),
                        status=response.status_code,
                        headers={key.lower(): value for key, value in response.headers.items()},
                        body=body,
                    )
            except FetchError:
                raise
            except httpx.TimeoutException:
                raise FetchError("timeout", transient=True) from None
            except httpx.HTTPError:
                raise FetchError("connect_failed", transient=True) from None
        raise FetchError("too_many_redirects")

    @staticmethod
    def _safe_url(url: str, code: str) -> str:
        try:
            return source_url(url)
        except ValueError:
            raise FetchError(code) from None

    async def _body(self, response: httpx.Response) -> bytes:
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > self.limits.max_response_bytes:
            raise FetchError("response_too_large")
        parts: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > self.limits.max_response_bytes:
                raise FetchError("response_too_large")
            if self.total_bytes + size > self.limits.max_total_bytes:
                raise FetchError("scan_budget_exceeded")
            parts.append(chunk)
        self.total_bytes += size
        return b"".join(parts)
