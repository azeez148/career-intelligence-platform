import asyncio
from collections.abc import AsyncIterator

import pytest
from extraction_helpers import FakeWeb, html

from app.integrations.browser import BrowserLimits, InterceptingRenderer, same_site
from app.integrations.http import Fetched, FetchError
from app.modules.extraction.runner import extract
from app.modules.extraction.strategies import ExtractionContext, SourceRef
from app.workers.extraction_tasks import browser_strategy

pytestmark = pytest.mark.browser
SPA = "https://spa-fixture.com/careers"


def script(body: str) -> tuple[int, str, bytes]:
    return 200, "application/javascript", body.encode()


def shell(*scripts: str) -> tuple[int, str, bytes]:
    tags = "".join(f'<script defer src="{src}"></script>' for src in scripts)
    return html(f"<!doctype html><html><head>{tags}</head><body><div id=root></div></body></html>")


@pytest.fixture
async def listener() -> AsyncIterator[tuple[int, list[str]]]:
    """A real private-address listener that must never receive a connection."""
    connections: list[str] = []

    async def accept(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        connections.append("connected")
        writer.close()

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        yield port, connections


def policy(web: FakeWeb):
    ctx = ExtractionContext(web.fetch)

    async def fetch(url: str, accept: str | None) -> Fetched | None:
        return await ctx.get(url, accept=accept)

    return fetch


def test_same_site_rule():
    assert same_site("careers.acme.com", "acme.com")
    assert same_site("careers.acme.com", "cdn.acme.com")
    assert same_site("acme.com", "static.acme.com")
    assert not same_site("careers.acme.com", "acme.com.evil.net")
    assert not same_site("acme.com", "other.com")


async def test_javascript_rendered_listing_is_extracted():
    web = FakeWeb(
        {
            SPA: shell("/static/app.js"),
            "https://spa-fixture.com/static/app.js": script(
                """
                const roles = [['101-platform-engineer', 'Platform Engineer'],
                               ['102-qa-analyst', 'QA Analyst'],
                               ['103-product-owner', 'Product Owner']];
                const list = document.createElement('ul');
                for (const [slug, title] of roles) {
                  const item = document.createElement('li');
                  const link = document.createElement('a');
                  link.href = '/careers/jobs/' + slug; link.textContent = title;
                  item.append(link); list.append(item);
                }
                document.getElementById('root').append(list);
                """
            ),
            "https://spa-fixture.com/careers/jobs/101-platform-engineer": html(
                "<main><h1>Platform Engineer</h1><p>Own the build system.</p></main>"
            ),
        }
    )
    outcome = await extract(SourceRef(SPA, None), ExtractionContext(web.fetch), browser_strategy)
    assert (outcome.status, outcome.strategy, outcome.confidence) == (
        "succeeded",
        "browser",
        "low",
    )
    titles = sorted(job.title for job in outcome.jobs)
    assert titles == ["Platform Engineer", "Product Owner", "QA Analyst"]
    assert {job.extraction_method for job in outcome.jobs} == {"browser"}
    platform = next(job for job in outcome.jobs if job.title == "Platform Engineer")
    assert platform.description_text == "Platform Engineer\n\nOwn the build system."


async def test_rendered_json_ld_is_medium_confidence():
    web = FakeWeb(
        {
            SPA: shell("/static/ld.js"),
            "https://spa-fixture.com/static/ld.js": script(
                """
                const tag = document.createElement('script');
                tag.type = 'application/ld+json';
                tag.textContent = JSON.stringify({'@type': 'JobPosting', title: 'Rendered Role',
                  url: 'https://spa-fixture.com/careers/rendered', employmentType: 'INTERN'});
                document.head.append(tag);
                """
            ),
        }
    )
    outcome = await extract(SourceRef(SPA, None), ExtractionContext(web.fetch), browser_strategy)
    assert (outcome.strategy, outcome.confidence) == ("browser", "medium")
    assert [(job.title, job.employment_type) for job in outcome.jobs] == [
        ("Rendered Role", "internship")
    ]


async def test_browser_never_reaches_private_cross_site_or_socket_targets(listener):
    port, connections = listener
    attack = f"""
    const target = 'http://127.0.0.1:{port}/';
    const attempts = [
      fetch(target).catch(() => 0),
      fetch('http://localhost:{port}/').catch(() => 0),
      fetch('https://other-host.com/collect').catch(() => 0),
      fetch('/careers/form', {{method: 'POST', body: 'x'}}).catch(() => 0),
    ];
    navigator.sendBeacon('/beacon', 'x');
    try {{ new WebSocket('ws://127.0.0.1:{port}/'); }} catch (e) {{}}
    try {{ new WebSocket('wss://spa-fixture.com/socket'); }} catch (e) {{}}
    const frame = document.createElement('iframe'); frame.src = target; document.body.append(frame);
    const image = new Image(); image.src = target;
    Promise.all(attempts).then(() => {{ document.body.dataset.done = '1'; }});
    """
    web = FakeWeb(
        {
            SPA: shell("/static/attack.js"),
            "https://spa-fixture.com/static/attack.js": script(attack),
        }
    )
    renderer = InterceptingRenderer(policy(web), BrowserLimits(settle_seconds=2))
    rendered = await renderer.render(SPA)
    await asyncio.sleep(0.5)
    assert connections == []
    requested = [url for url, _ in web.requests]
    assert not any(
        "127.0.0.1" in url or "localhost" in url or "other-host" in url for url in requested
    )
    assert not any(url.endswith(("/careers/form", "/beacon")) for url in requested)
    blocked = set(rendered.stats.blocked)
    assert {"url_blocked", "cross_site_blocked", "method_blocked", "websocket_blocked"} <= blocked


async def test_request_budget_and_total_time_are_enforced():
    many = "".join(f"fetch('/data/{index}.json').catch(() => 0);" for index in range(30))
    web = FakeWeb(
        {SPA: shell("/static/many.js"), "https://spa-fixture.com/static/many.js": script(many)}
    )
    rendered = await InterceptingRenderer(policy(web), BrowserLimits(max_requests=5)).render(SPA)
    assert rendered.stats.requests == 5
    assert "browser_budget_exceeded" in rendered.stats.blocked

    async def slow(url: str, accept: str | None) -> Fetched | None:
        await asyncio.sleep(30)
        return None

    with pytest.raises(FetchError) as caught:
        await InterceptingRenderer(slow, BrowserLimits(total_seconds=2)).render(SPA)
    assert caught.value.code == "render_timeout" and caught.value.transient


async def test_dialogs_popups_and_redirects_do_not_stall_rendering():
    redirected = "https://spa-fixture.com/careers/en"

    body = b"<p id=ok>Loaded</p><script>alert('x'); window.open('/popup'); confirm('y');</script>"

    async def fetch(url: str, accept: str | None) -> Fetched | None:
        # Like SafeHttpClient: a redirect chain returns the final URL and its document.
        if url in {SPA, redirected}:
            return Fetched(redirected, 200, {"content-type": "text/html"}, body)
        return None

    rendered = await InterceptingRenderer(fetch, BrowserLimits(settle_seconds=1)).render(SPA)
    assert rendered.url == redirected and "Loaded" in rendered.html


async def test_failed_navigation_is_reported_safely():
    web = FakeWeb({})
    with pytest.raises(FetchError) as caught:
        await InterceptingRenderer(policy(web)).render(SPA)
    assert caught.value.code == "render_failed" and not caught.value.transient
