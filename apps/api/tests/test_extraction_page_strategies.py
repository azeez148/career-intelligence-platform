import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pytest
from extraction_helpers import FIXTURES, FakeWeb, html

from app.modules.extraction.runner import extract
from app.modules.extraction.strategies import (
    ExtractionContext,
    ExtractionLimits,
    SourceRef,
    static_html,
)
from app.modules.extraction.strategies.structured_data import postings

SITES = FIXTURES / "sites"
EXPECTED = FIXTURES / "expected"


def site(name: str) -> tuple[str, FakeWeb]:
    root = SITES / name
    spec = json.loads((root / "site.json").read_text())
    pages = {
        url: (200, "text/html; charset=utf-8", (root / file).read_bytes())
        for url, file in spec["pages"].items()
    }
    return spec["start"], FakeWeb(pages)


async def run_site(name: str, limits: ExtractionLimits | None = None):
    start, web = site(name)
    outcome = await extract(
        SourceRef(start, None), ExtractionContext(web.fetch, limits), static_html.extract
    )
    return outcome, web


def snapshot(outcome) -> dict:
    return {
        "status": outcome.status,
        "strategy": outcome.strategy,
        "confidence": outcome.confidence,
        "complete": outcome.complete,
        "failure_code": outcome.failure_code,
        "jobs": [
            asdict(job) | {"dedupe_key": job.dedupe_key(None), "fingerprint": job.fingerprint()}
            for job in outcome.jobs
        ],
    }


@pytest.mark.parametrize(
    "name", ["jsonld-listing", "static-listing", "js-shell", "navigation-only"]
)
async def test_source_fixture_regression(name):
    """Pinned normalized output per fixture site; parser changes show up as reviewable diffs."""
    outcome, _ = await run_site(name)
    actual = json.loads(json.dumps(snapshot(outcome), default=str))
    expected_path = EXPECTED / f"{name}.json"
    assert expected_path.exists(), f"missing reviewed snapshot {expected_path.name}"
    assert actual == json.loads(expected_path.read_text())


async def test_json_ld_listing_maps_structured_fields():
    outcome, web = await run_site("jsonld-listing")
    assert (outcome.status, outcome.strategy, outcome.confidence) == (
        "succeeded",
        "structured_data",
        "medium",
    )
    sre, recruiter = outcome.jobs
    assert sre.canonical_url == "https://jsonld-fixture.com/careers/sre"
    assert (sre.source_job_id, sre.work_mode, sre.employment_type) == (
        "SRE-7",
        "remote",
        "full_time",
    )
    assert sre.location_text == "Lisbon, PT"
    assert sre.requirements_text == "- Linux\n- On-call experience"
    assert sre.valid_through == datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
    # A posting without its own URL points at the page that carried it.
    assert recruiter.canonical_url == "https://jsonld-fixture.com/careers"
    assert recruiter.dedupe_key(None) == "https://jsonld-fixture.com/careers#88"
    assert sre.dedupe_key(None) == "https://jsonld-fixture.com/careers/sre"
    assert recruiter.location_text == "Porto, Norte, Portugal; Remote within the EU"
    assert (recruiter.source_job_id, recruiter.employment_type) == ("88", "part_time")
    assert recruiter.requirements_text == "Two years of recruiting."
    assert recruiter.field_sources["requirements_text"] == "structured"
    assert web.fetched() == ["https://jsonld-fixture.com/careers"]


async def test_static_listing_follows_pagination_and_prefers_detail_json_ld():
    outcome, web = await run_site("static-listing")
    assert (outcome.status, outcome.strategy, outcome.confidence) == (
        "succeeded",
        "static_html",
        "low",
    )
    by_title = {job.title: job for job in outcome.jobs}
    assert sorted(by_title) == [
        "Backend Engineer",
        "Data Analyst (Hybrid)",
        "Design Lead",
        "Support Lead",
    ]
    backend = by_title["Backend Engineer"]
    assert (backend.confidence, backend.employment_type, backend.location_text) == (
        "medium",
        "contract",
        "Nairobi, KE",
    )
    assert backend.canonical_url == "https://static-fixture.com/careers/jobs/101-backend-engineer"
    assert backend.dedupe_key(None) == backend.canonical_url
    analyst = by_title["Data Analyst (Hybrid)"]
    # Heuristic fields: headings and layout are not mistaken for structured values.
    assert analyst.work_mode == "unknown" and analyst.requirements_text == "- SQL"
    assert analyst.description_text is not None
    assert "Turn data into decisions." in analyst.description_text
    for noise in ("Site header text", "Navigation text", "Footer text", "track()"):
        assert noise not in analyst.description_text
    # A missing detail page keeps the listing title and no invented description.
    assert by_title["Design Lead"].description_text is None
    assert by_title["Design Lead"].canonical_url.endswith("/careers/jobs/103-design-lead")
    fetched = web.fetched()
    assert fetched.count("https://static-fixture.com/careers?page=2") == 1
    assert not any(
        "other-host.com" in url or "/blog/" in url or "/search" in url for url in fetched
    )


async def test_detail_and_listing_limits_are_enforced():
    outcome, web = await run_site(
        "static-listing", ExtractionLimits(max_listing_pages=1, max_detail_pages=1)
    )
    assert outcome.status == "partial" and outcome.complete is False
    assert len(outcome.jobs) == 3
    details = [url for url in web.fetched() if "/careers/jobs/" in url]
    assert len(details) == 1
    capped, _ = await run_site("static-listing", ExtractionLimits(max_jobs=2))
    assert capped.status == "partial" and len(capped.jobs) == 2


async def test_js_shell_requests_browser_and_navigation_page_is_unsupported():
    shell, _ = await run_site("js-shell")
    assert (shell.status, shell.escalate) == ("queued", True)
    navigation, _ = await run_site("navigation-only")
    assert (navigation.status, navigation.failure_code) == ("unsupported", "no_jobs_recognized")


async def test_non_html_and_malformed_documents_are_handled():
    web = FakeWeb(
        {
            "https://pdf-fixture.com/careers": (200, "application/pdf", b"%PDF-1.7"),
            "https://broken-fixture.com/careers": html("<html><a href='/jobs/1-x'>" * 5000),
        }
    )
    pdf = await extract(
        SourceRef("https://pdf-fixture.com/careers", None),
        ExtractionContext(web.fetch),
        static_html.extract,
    )
    assert (pdf.status, pdf.failure_code) == ("unsupported", "no_jobs_recognized")
    broken = await extract(
        SourceRef("https://broken-fixture.com/careers", None),
        ExtractionContext(web.fetch),
        static_html.extract,
    )
    assert broken.status in {"succeeded", "unsupported"}
    assert postings('<script type="application/ld+json">' + "[" * 10_000 + "</script>") == []


def test_expected_snapshots_exist_for_every_site():
    assert {path.name for path in SITES.iterdir()} == {
        Path(name).stem for name in (p.name for p in EXPECTED.glob("*.json"))
    }
