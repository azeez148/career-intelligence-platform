"""schema.org JobPosting extraction from JSON-LD blocks."""

import json
from html.parser import HTMLParser
from typing import Any

from app.modules.jobs.normalize import (
    MAX_LOCATION,
    MAX_SHORT,
    NormalizedJob,
    build,
    employment_type,
    html_to_text,
    plain,
    requirements_from_html,
    timestamp,
    work_mode,
)

MAX_BLOCKS = 50
MAX_BLOCK_SIZE = 1_000_000
MAX_POSTINGS = 1000
MAX_DEPTH = 6


class _JsonLdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.blocks: list[str] = []
        self._current: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "").strip().lower() for key, value in attrs}
        if tag.lower() == "script" and values.get("type") == "application/ld+json":
            self._current = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._current is not None:
            if len(self.blocks) < MAX_BLOCKS:
                self.blocks.append("".join(self._current)[:MAX_BLOCK_SIZE])
            self._current = None

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current.append(data)


def _is_posting(node: dict[str, Any]) -> bool:
    kind = node.get("@type")
    kinds = kind if isinstance(kind, list) else [kind]
    return "JobPosting" in kinds


def _walk(node: object, found: list[dict[str, Any]], depth: int = 0) -> None:
    if depth > MAX_DEPTH or len(found) >= MAX_POSTINGS:
        return
    if isinstance(node, list):
        for item in node:
            _walk(item, found, depth + 1)
    elif isinstance(node, dict):
        if _is_posting(node):
            found.append(node)
        elif "@graph" in node:
            _walk(node["@graph"], found, depth + 1)
        elif isinstance(node.get("itemListElement"), list):
            for element in node["itemListElement"]:
                _walk(element.get("item") if isinstance(element, dict) else None, found, depth + 1)


def postings(document: str) -> list[dict[str, Any]]:
    """Return JobPosting nodes; malformed blocks are skipped individually."""
    parser = _JsonLdParser()
    parser.feed(document[:5_000_000])
    parser.close()
    found: list[dict[str, Any]] = []
    for block in parser.blocks:
        try:
            _walk(json.loads(block), found)
        except (ValueError, RecursionError):
            continue
    return found


def _text(value: object) -> str | None:
    if isinstance(value, dict):
        value = value.get("name") or value.get("value")
    return value if isinstance(value, str) else None


def location_text(value: object) -> str | None:
    places = value if isinstance(value, list) else [value]
    labels: list[str] = []
    for place in places[:20]:
        if not isinstance(place, dict):
            continue
        address = place.get("address")
        if isinstance(address, dict):
            parts = [
                _text(address.get(key))
                for key in ("addressLocality", "addressRegion", "addressCountry")
            ]
            label = ", ".join(part.strip() for part in parts if part and part.strip())
        else:
            label = _text(address) or _text(place) or ""
        if label and label not in labels:
            labels.append(label)
    return plain("; ".join(labels), MAX_LOCATION)


def identifier(value: object) -> str | None:
    if isinstance(value, dict):
        value = value.get("value")
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return plain(value, MAX_SHORT)


def structured_requirements(node: dict[str, Any]) -> str | None:
    parts: list[str] = []
    for key in ("qualifications", "experienceRequirements", "skills", "educationRequirements"):
        value = node.get(key)
        values = value if isinstance(value, list) else [value]
        for item in values:
            text = html_to_text(_text(item))
            if text:
                parts.append(text)
    return "\n\n".join(parts) or None


def to_job(
    node: dict[str, Any], page_url: str, method: str = "structured_data"
) -> NormalizedJob | None:
    description = _text(node.get("description"))
    structured = structured_requirements(node)
    remote = (_text(node.get("jobLocationType")) or "").upper() == "TELECOMMUTE"
    sources = dict.fromkeys(
        (
            "title",
            "source_job_id",
            "location_text",
            "employment_type",
            "description_text",
            "posted_at",
            "valid_through",
            "department",
        ),
        "structured",
    )
    sources |= {
        "canonical_url": "structured" if isinstance(node.get("url"), str) else "page",
        "work_mode": "structured",
        "requirements_text": "structured" if structured else "heuristic",
    }
    own_url = isinstance(node.get("url"), str)
    job = build(
        url=node["url"] if own_url else page_url,
        base=page_url,
        title=_text(node.get("title")),
        method=method,
        confidence="medium",
        sources=sources,
        source_job_id=identifier(node.get("identifier")),
        location_text=location_text(node.get("jobLocation")),
        work_mode="remote" if remote else work_mode(_text(node.get("workMode"))),
        employment_type=employment_type(node.get("employmentType")),
        department=plain(_text(node.get("occupationalCategory")), MAX_SHORT),
        description_text=html_to_text(description),
        requirements_text=structured or requirements_from_html(description),
        posted_at=timestamp(node.get("datePosted")),
        valid_through=timestamp(node.get("validThrough")),
    )
    if job is not None and not own_url:
        job.shared_url = True
    return job
