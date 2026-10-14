from datetime import UTC, datetime

import pytest
from extraction_helpers import FakeWeb, fixture, html, json_page

from app.integrations.http import JSON_ACCEPT, FetchError
from app.modules.extraction.runner import extract
from app.modules.extraction.strategies import ExtractionContext, ExtractionLimits, SourceRef
from app.modules.extraction.strategies.greenhouse import board_token, embedded_token
from app.modules.extraction.strategies.lever import embedded_site, site_ref
from app.modules.jobs.normalize import (
    canonical_job_url,
    employment_type,
    html_to_text,
    requirements_from_html,
    timestamp,
    work_mode,
)

GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards/acmefixture/jobs?content=true"
LEVER_API = "https://api.lever.co/v0/postings/acmefixture?mode=json&skip={skip}&limit=100"


def test_html_to_text_keeps_structure_and_drops_active_content():
    text = html_to_text(
        "<h2>About</h2><p>We &amp; you.</p><script>steal()</script><style>p{}</style>"
        "<ul><li>One</li><li> Two </li><li></li></ul><iframe src=x>bad</iframe>tail"
    )
    assert text == "About\n\nWe & you.\n\n- One\n- Two\ntail"
    assert html_to_text("") is None and html_to_text("<script>x</script>") is None
    assert 90 <= len(html_to_text("<p>" + "a" * 500 + "</p>", limit=100) or "") <= 100


def test_requirements_only_come_from_labelled_sections():
    content = (
        "<p>Intro mentioning requirements casually.</p><h3>Requirements</h3><ul><li>Go</li></ul>"
        "<h3>Benefits</h3><p>Pension</p><p><strong>Qualifications</strong></p><ul><li>BSc</li></ul>"
    )
    assert requirements_from_html(content) == "- Go\n\n- BSc"
    assert requirements_from_html("<p>No labelled sections here.</p>") is None


def test_value_mapping_is_exact_and_never_guessed():
    assert work_mode("Remote") == "remote" and work_mode("on-site") == "onsite"
    assert work_mode("Remote - US") == "unknown" and work_mode(None) == "unknown"
    assert (
        employment_type("FULL_TIME") == "full_time" and employment_type("Full-time") == "full_time"
    )
    assert employment_type(["FULL_TIME", "CONTRACTOR"]) == "unknown"
    assert employment_type(["FULL_TIME", "OTHER"]) == "full_time"
    assert employment_type("Seasonal") == "unknown"
    assert timestamp(1788220800000) == datetime(2026, 9, 1, tzinfo=UTC)
    assert timestamp("2026-09-01") == datetime(2026, 9, 1, tzinfo=UTC)
    assert timestamp("next week") is None and timestamp(True) is None


def test_canonical_job_urls_drop_fragments_and_tracking_only():
    assert (
        canonical_job_url("https://Jobs.Example.com/a?id=7&utm_source=x&gclid=y#apply")
        == "https://jobs.example.com/a?id=7"
    )
    assert canonical_job_url("/jobs/9", "https://acme.com/careers") == "https://acme.com/jobs/9"
    with pytest.raises(ValueError):
        canonical_job_url("javascript:alert(1)")
    with pytest.raises(ValueError):
        canonical_job_url("http://127.0.0.1/job")


def test_platform_references_are_parsed_strictly():
    assert board_token("https://boards.greenhouse.io/acmefixture") == "acmefixture"
    assert board_token("https://job-boards.greenhouse.io/acme/jobs/1") == "acme"
    assert board_token("https://boards.greenhouse.io/embed/job_board?for=acme") == "acme"
    assert board_token("https://boards-api.greenhouse.io/v1/boards/acme/jobs") == "acme"
    assert board_token("https://boards.greenhouse.io/") is None
    assert board_token("https://evil.com/acme") is None
    assert board_token("https://boards.greenhouse.io/embed/job_board?for=a/../b") is None
    assert site_ref("https://jobs.lever.co/acme/123") == ("api.lever.co", "acme")
    assert site_ref("https://jobs.eu.lever.co/acme") == ("api.eu.lever.co", "acme")
    assert site_ref("https://api.lever.co/v0/postings/acme") == ("api.lever.co", "acme")
    assert site_ref("https://jobs.lever.co.evil.com/acme") is None
    page = '<script src="https://boards.greenhouse.io/embed/job_board/js?for=embedded&amp;x=1">'
    assert embedded_token(page) == "embedded"
    assert embedded_site('<a href="https://jobs.lever.co/lever-co">') == (
        "api.lever.co",
        "lever-co",
    )


async def test_greenhouse_api_normalizes_without_fabrication():
    web = FakeWeb({GREENHOUSE_API: json_page(fixture("greenhouse_jobs.json"))})
    outcome = await extract(
        SourceRef("https://boards.greenhouse.io/acmefixture", "greenhouse"),
        ExtractionContext(web.fetch),
    )
    assert (outcome.status, outcome.strategy, outcome.confidence) == (
        "succeeded",
        "ats_api",
        "high",
    )
    assert outcome.complete and len(outcome.jobs) == 2
    first, second = outcome.jobs
    assert first.title == "Senior Backend Engineer"
    assert first.canonical_url == "https://boards.greenhouse.io/acmefixture/jobs/4012001?gh_src=abc"
    assert (first.source_job_id, first.location_text, first.work_mode) == (
        "4012001",
        "Remote",
        "remote",
    )
    assert first.department == "Engineering, Platform"
    assert first.description_text is not None and "alert" not in first.description_text
    assert first.requirements_text == "- Python\n- PostgreSQL"
    assert first.posted_at == datetime(2026, 9, 1, 9, tzinfo=UTC)
    assert first.dedupe_key("greenhouse") == "greenhouse:4012001"
    # Missing values stay missing; updated_at is not a posting date.
    assert (second.description_text, second.posted_at, second.department) == (None, None, None)
    assert (second.work_mode, second.employment_type) == ("unknown", "unknown")
    assert "description_text" not in second.field_sources
    assert web.requests[-1] == (GREENHOUSE_API, JSON_ACCEPT)


async def test_lever_api_paginates_and_maps_fields():
    web = FakeWeb(
        {
            LEVER_API.format(skip=0): json_page(fixture("lever_page1.json")),
            LEVER_API.format(skip=100): json_page(fixture("lever_page2.json")),
        }
    )
    outcome = await extract(
        SourceRef("https://jobs.lever.co/acmefixture", "lever"), ExtractionContext(web.fetch)
    )
    assert outcome.status == "succeeded" and outcome.complete and len(outcome.jobs) == 102
    job = outcome.jobs[0]
    assert (job.work_mode, job.employment_type, job.department) == ("hybrid", "full_time", "Data")
    assert job.requirements_text == "- SQL\n- Statistics"
    assert job.description_text and "Equal opportunity." in job.description_text
    last = outcome.jobs[-1]
    assert (last.work_mode, last.employment_type, last.location_text) == (
        "unknown",
        "unknown",
        None,
    )


async def test_lever_page_limit_reports_partial_listing():
    web = FakeWeb({LEVER_API.format(skip=0): json_page(fixture("lever_page1.json"))})
    outcome = await extract(
        SourceRef("https://jobs.lever.co/acmefixture", "lever"),
        ExtractionContext(web.fetch, ExtractionLimits(max_listing_pages=1)),
    )
    assert (outcome.status, outcome.complete, len(outcome.jobs)) == ("partial", False, 100)


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (404, b"", ("unsupported", "source_not_found")),
        (403, b"", ("unsupported", "api_unavailable")),
        (200, b"{not json", ("unsupported", "malformed_content")),
        (200, b'{"jobs": "nope"}', ("unsupported", "malformed_content")),
    ],
)
async def test_api_errors_are_reported_safely(status, body, expected):
    web = FakeWeb({GREENHOUSE_API: (status, "application/json", body)})
    outcome = await extract(
        SourceRef("https://boards.greenhouse.io/acmefixture", "greenhouse"),
        ExtractionContext(web.fetch),
    )
    assert (outcome.status, outcome.failure_code) == expected


async def test_api_rate_limits_and_server_errors_are_transient():
    web = FakeWeb({GREENHOUSE_API: (503, "text/plain", b"busy")})
    with pytest.raises(FetchError) as caught:
        await extract(
            SourceRef("https://boards.greenhouse.io/acmefixture", "greenhouse"),
            ExtractionContext(web.fetch),
        )
    assert caught.value.code == "api_unavailable" and caught.value.transient


async def test_robots_disallow_on_api_host_is_respected():
    web = FakeWeb(
        {
            "https://boards-api.greenhouse.io/robots.txt": (
                200,
                "text/plain",
                b"User-agent: *\nDisallow: /",
            )
        }
    )
    outcome = await extract(
        SourceRef("https://boards.greenhouse.io/acmefixture", "greenhouse"),
        ExtractionContext(web.fetch),
    )
    assert (outcome.status, outcome.failure_code) == ("unsupported", "robots_disallowed")
    assert web.fetched() == []


async def test_embedded_board_on_company_page_uses_the_public_api():
    web = FakeWeb(
        {
            "https://acme.com/careers": html(
                '<div id="grnhse_app"></div><script '
                'src="https://boards.greenhouse.io/embed/job_board/js?for=acmefixture"></script>'
            ),
            GREENHOUSE_API: json_page(fixture("greenhouse_jobs.json")),
        }
    )
    outcome = await extract(
        SourceRef("https://acme.com/careers", "greenhouse"), ExtractionContext(web.fetch)
    )
    assert outcome.status == "succeeded" and len(outcome.jobs) == 2
    assert web.fetched() == ["https://acme.com/careers", GREENHOUSE_API]


async def test_unrecognized_generic_page_without_page_strategy_is_unsupported():
    web = FakeWeb({"https://acme.com/careers": html("<p>No jobs here</p>")})
    outcome = await extract(
        SourceRef("https://acme.com/careers", None), ExtractionContext(web.fetch)
    )
    assert (outcome.status, outcome.failure_code) == ("unsupported", "no_jobs_recognized")
    missing = await extract(SourceRef("https://acme.com/gone", None), ExtractionContext(web.fetch))
    assert (missing.status, missing.failure_code) == ("unsupported", "source_not_found")
