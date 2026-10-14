from collections.abc import Iterable

import httpcore
import httpx
import pytest
from httpcore._backends.base import SOCKET_OPTION

from app.integrations.http import (
    FetchError,
    FetchLimits,
    PinnedNetworkBackend,
    SafeHttpClient,
    public_addresses,
)


class FakeStream(httpcore.AsyncNetworkStream):
    def __init__(self, peer: str) -> None:
        self.peer = peer
        self.closed = False

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:  # noqa: ASYNC109
        return b""

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:  # noqa: ASYNC109
        return None

    async def aclose(self) -> None:
        self.closed = True

    async def start_tls(
        self,
        ssl_context: object,
        server_hostname: bytes | None = None,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> httpcore.AsyncNetworkStream:
        return self

    def get_extra_info(self, info: str) -> object:
        return (self.peer, 443) if info == "server_addr" else None


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.1", "169.254.1.1", "::1", "fc00::1", "not-an-ip"],
)
def test_public_addresses_reject_every_non_public_result(address: str):
    with pytest.raises(FetchError):
        public_addresses(["93.184.216.34", address])


def test_public_addresses_require_dns_and_deduplicate():
    assert public_addresses(["93.184.216.34", "93.184.216.34"]) == ["93.184.216.34"]
    with pytest.raises(FetchError, match="dns_unavailable"):
        public_addresses([])


async def test_backend_connects_to_resolved_address_and_verifies_peer():
    calls: list[str] = []

    async def resolve(host: str, port: int) -> list[str]:
        assert (host, port) == ("example.com", 443)
        return ["93.184.216.34"]

    async def connect(  # noqa: ASYNC109 -- connector contract
        host: str,
        port: int,
        timeout: float | None,  # noqa: ASYNC109 -- connector contract
        local_address: str | None,
        socket_options: Iterable[SOCKET_OPTION] | None,
    ) -> httpcore.AsyncNetworkStream:
        calls.append(host)
        return FakeStream(host)

    backend = PinnedNetworkBackend(resolve, connect)
    stream = await backend.connect_tcp("example.com", 443)
    assert calls == ["93.184.216.34"]
    assert stream.get_extra_info("server_addr") == ("93.184.216.34", 443)


async def test_backend_rejects_peer_changes_and_ip_hostnames():
    stream = FakeStream("93.184.216.35")

    async def resolve(host: str, port: int) -> list[str]:
        return ["93.184.216.34"]

    async def connect(  # noqa: ASYNC109 -- connector contract
        host: str,
        port: int,
        timeout: float | None,  # noqa: ASYNC109 -- connector contract
        local_address: str | None,
        socket_options: Iterable[SOCKET_OPTION] | None,
    ) -> httpcore.AsyncNetworkStream:
        return stream

    backend = PinnedNetworkBackend(resolve, connect)
    with pytest.raises(FetchError, match="peer_mismatch"):
        await backend.connect_tcp("example.com", 443)
    assert stream.closed
    with pytest.raises(FetchError, match="dns_blocked"):
        await backend.connect_tcp("127.0.0.1", 80)


async def test_safe_client_checks_redirects_limits_and_rate_callback():
    requested: list[str] = []
    limited: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.path == "/":
            return httpx.Response(302, headers={"location": "/careers"})
        return httpx.Response(200, content=b"careers")

    async def rate_limit(host: str) -> None:
        limited.append(host)

    async with SafeHttpClient(
        transport=httpx.MockTransport(handler), rate_limit=rate_limit
    ) as client:
        response = await client.fetch("https://example.com")
    assert response.url == "https://example.com/careers"
    assert response.body == b"careers"
    assert requested == ["https://example.com/", "https://example.com/careers"]
    assert limited == ["example.com", "example.com"]

    async def unsafe_redirect(_: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    async with SafeHttpClient(transport=httpx.MockTransport(unsafe_redirect)) as client:
        with pytest.raises(FetchError, match="redirect_invalid"):
            await client.fetch("https://example.com")


async def test_safe_client_enforces_body_and_response_budgets():
    async def large(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"12345")

    limits = FetchLimits(max_response_bytes=4, max_total_bytes=10)
    async with SafeHttpClient(limits=limits, transport=httpx.MockTransport(large)) as client:
        with pytest.raises(FetchError, match="response_too_large"):
            await client.fetch("https://example.com")

    async def redirect(_: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/again"})

    limits = FetchLimits(max_responses=1)
    async with SafeHttpClient(limits=limits, transport=httpx.MockTransport(redirect)) as client:
        with pytest.raises(FetchError, match="response_budget_exceeded"):
            await client.fetch("https://example.com")


async def test_test_host_allowlist_is_exact_and_still_pins_the_peer():
    resolved: list[str] = []

    async def resolve(host: str, port: int) -> list[str]:
        resolved.append(host)
        return ["172.18.0.5"]

    async def connect(  # noqa: ASYNC109 -- connector contract
        host: str,
        port: int,
        timeout: float | None,  # noqa: ASYNC109 -- connector contract
        local_address: str | None,
        socket_options: Iterable[SOCKET_OPTION] | None,
    ) -> httpcore.AsyncNetworkStream:
        return FakeStream(host)

    backend = PinnedNetworkBackend(resolve, connect, {"jobs-fixture.com": "fixture-site"})
    stream = await backend.connect_tcp("jobs-fixture.com", 80)
    assert resolved == ["fixture-site"]
    assert stream.get_extra_info("server_addr") == ("172.18.0.5", 443)
    for host in ("www.jobs-fixture.com", "jobs-fixture.com.evil.net", "other.com"):
        with pytest.raises(FetchError, match="dns_blocked"):
            await backend.connect_tcp(host, 80)


def test_test_host_allowlist_is_refused_in_production(monkeypatch):
    from pydantic import SecretStr, ValidationError

    from app.core.config import Settings

    values = {
        "database_url": SecretStr("postgresql+asyncpg://user:pass@db:5432/app"),
        "allowed_origins": ["https://app.example.org"],
        "redis_url": SecretStr("redis://:secret@redis:6379/0"),
        "_env_file": None,
    }
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(ValidationError, match="only allowed in development"):
        Settings(outbound_test_hosts={"jobs-fixture.com": "fixture-site"}, **values)
    monkeypatch.setenv("ENVIRONMENT", "development")
    with pytest.raises(ValidationError, match="exact lowercase hostnames"):
        Settings(outbound_test_hosts={"Jobs-Fixture.com": "fixture-site"}, **values)
    assert Settings(outbound_test_hosts={"jobs-fixture.com": "fixture-site"}, **values)
