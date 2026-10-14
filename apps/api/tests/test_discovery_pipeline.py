from collections.abc import Awaitable, Callable

import pytest

from app.integrations.http import Fetched, FetchError
from app.modules.discovery.ats import platform_for
from app.modules.discovery.candidates import name_candidate
from app.modules.discovery.html import parse_document
from app.modules.discovery.pipeline import DiscoveryPipeline
from app.modules.discovery.sitemaps import parse_sitemap


def page(url: str, body: str, content_type: str = "text/html", status: int = 200) -> Fetched:
    return Fetched(url, status, {"content-type": content_type}, body.encode())


def fixtures(values: dict[str, Fetched]) -> tuple[Callable[[str], Awaitable[Fetched]], list[str]]:
    calls: list[str] = []

    async def fetch(url: str) -> Fetched:
        calls.append(url)
        return values.get(url, page(url, "", status=404))

    return fetch, calls


async def test_pipeline_follows_homepage_signal_and_recognizes_lever():
    fetch, calls = fixtures(
        {
            "https://acme.com/robots.txt": page(
                "https://acme.com/robots.txt", "User-agent: *\nAllow: /", "text/plain"
            ),
            "https://acme.com/": page(
                "https://acme.com/", '<a href="https://jobs.lever.co/acme">Open jobs</a>'
            ),
            "https://jobs.lever.co/robots.txt": page(
                "https://jobs.lever.co/robots.txt", "User-agent: *\nAllow: /", "text/plain"
            ),
            "https://jobs.lever.co/acme": page("https://jobs.lever.co/acme", "Jobs at Acme"),
        }
    )
    outcome = await DiscoveryPipeline(fetch).run("https://acme.com")
    assert outcome.status == "succeeded"
    assert outcome.resolved_website_url == "https://acme.com/"
    assert [(item.platform, item.discovery_method) for item in outcome.sources] == [
        ("lever", "homepage_link")
    ]
    assert "https://jobs.lever.co/acme" in calls


async def test_pipeline_uses_sitemap_and_obeys_robots():
    fetch, calls = fixtures(
        {
            "https://acme.com/robots.txt": page(
                "https://acme.com/robots.txt",
                "User-agent: *\nDisallow: /private\nSitemap: https://acme.com/map.xml",
                "text/plain",
            ),
            "https://acme.com/": page("https://acme.com/", "Home"),
            "https://acme.com/map.xml": page(
                "https://acme.com/map.xml",
                "<urlset><url><loc>https://acme.com/careers</loc></url>"
                "<url><loc>https://acme.com/private/jobs</loc></url></urlset>",
                "application/xml",
            ),
            "https://acme.com/careers": page("https://acme.com/careers", "Careers"),
        }
    )
    outcome = await DiscoveryPipeline(fetch).run("https://acme.com")
    assert outcome.status == "succeeded"
    assert [source.url for source in outcome.sources] == ["https://acme.com/careers"]
    assert "https://acme.com/private/jobs" not in calls


async def test_pipeline_reports_policy_content_and_temporary_failures():
    fetch, _ = fixtures(
        {
            "https://acme.com/robots.txt": page(
                "https://acme.com/robots.txt", "User-agent: *\nDisallow: /", "text/plain"
            )
        }
    )
    outcome = await DiscoveryPipeline(fetch).run("https://acme.com")
    assert (outcome.status, outcome.failure_code) == ("unsupported", "robots_disallowed")

    fetch, _ = fixtures(
        {
            "https://acme.com/robots.txt": page(
                "https://acme.com/robots.txt", "User-agent: *\nAllow: /", "text/plain"
            ),
            "https://acme.com/": page("https://acme.com/", "binary", "application/octet-stream"),
        }
    )
    outcome = await DiscoveryPipeline(fetch).run("https://acme.com")
    assert outcome.failure_code == "unsupported_content"

    fetch, _ = fixtures(
        {
            "https://acme.com/robots.txt": page(
                "https://acme.com/robots.txt", "User-agent: *\nAllow: /", "text/plain"
            ),
            "https://acme.com/": page("https://acme.com/", "busy", status=503),
        }
    )
    with pytest.raises(FetchError) as error:
        await DiscoveryPipeline(fetch).run("https://acme.com")
    assert error.value.transient and error.value.code == "remote_temporary"


def test_bounded_parsers_candidates_and_ats_classification():
    assert name_candidate("  Example Team ") == "https://exampleteam.com/"
    assert name_candidate("\u6771\u4eac") is None
    assert platform_for("https://boards.greenhouse.io/acme") == "greenhouse"
    assert platform_for("https://acme.wd1.myworkdayjobs.com/jobs") == "workday"
    malformed = parse_sitemap(
        b"<!DOCTYPE x [<!ENTITY e SYSTEM 'file:///secret'>]><urlset>&e;</urlset>"
    )
    assert malformed.urls == malformed.nested == []
    many = (
        "<urlset>"
        + "".join(f"<url><loc>https://a.com/{n}</loc></url>" for n in range(4))
        + "</urlset>"
    )
    assert len(parse_sitemap(many.encode(), max_urls=2).urls) == 2
    canonical, _, _ = parse_document(
        b'<link rel="canonical" href="https://unrelated.com/">', "https://acme.com/"
    )
    assert canonical == "https://acme.com/"
