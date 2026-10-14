"""Pure normalization of extracted job data. Missing values stay missing."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from app.core.urls import source_url

MAX_DESCRIPTION = 100_000
MAX_TITLE = 500
MAX_SHORT = 255
MAX_LOCATION = 500

SKIPPED = {"script", "style", "noscript", "template", "svg", "head", "iframe", "object"}
BLOCKS = {
    "p", "div", "section", "article", "br", "tr", "table", "ul", "ol", "header", "footer",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "dl", "dt", "dd", "main",
}  # fmt: skip
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
TRACKING = re.compile(r"^(utm_[a-z0-9_]+|gclid|fbclid|msclkid|mc_cid|mc_eid|_hsenc|_hsmi)$", re.I)
REQUIREMENTS = re.compile(
    r"\b(requirements?|qualifications?|what you(?:'ll| will)? (?:need|bring)|"
    r"who you are|skills (?:and|&) experience|must[- ]haves?)\b",
    re.I,
)

WORK_MODES = {
    "remote": "remote",
    "fully remote": "remote",
    "telecommute": "remote",
    "work from home": "remote",
    "hybrid": "hybrid",
    "onsite": "onsite",
    "on-site": "onsite",
    "on site": "onsite",
    "in office": "onsite",
    "in-office": "onsite",
}
EMPLOYMENT_TYPES = {
    "full_time": "full_time",
    "full-time": "full_time",
    "full time": "full_time",
    "fulltime": "full_time",
    "permanent": "full_time",
    "part_time": "part_time",
    "part-time": "part_time",
    "part time": "part_time",
    "contract": "contract",
    "contractor": "contract",
    "temporary": "temporary",
    "temp": "temporary",
    "intern": "internship",
    "internship": "internship",
}
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


class _TextParser(HTMLParser):
    def __init__(self, limit: int) -> None:
        super().__init__(convert_charrefs=True)
        self.limit = limit
        self.size = 0
        self.parts: list[str] = []
        self.skip = 0
        self.sections: list[tuple[str, list[str]]] = [("", [])]
        self._heading: list[str] | None = None
        self._strong: list[str] | None = None

    def _emit(self, text: str, section: bool = True) -> None:
        if self.size >= self.limit:
            return
        text = text[: self.limit - self.size]
        self.size += len(text)
        self.parts.append(text)
        if section:
            self.sections[-1][1].append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in SKIPPED:
            self.skip += 1
        elif self.skip:
            return
        elif tag in HEADINGS:
            self._heading = []
            self._emit("\n\n")
        elif tag in {"strong", "b"}:
            self._strong = []
        elif tag == "li":
            self._emit("\n- ")
        elif tag in BLOCKS:
            self._emit("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in SKIPPED:
            self.skip = max(self.skip - 1, 0)
        elif self.skip:
            return
        elif tag in HEADINGS and self._heading is not None:
            self.sections.append((" ".join("".join(self._heading).split()), []))
            self._heading = None
            self._emit("\n")
        elif tag in {"strong", "b"} and self._strong is not None:
            label = " ".join("".join(self._strong).split())
            # A short bold line acts as a section label in many listings.
            if 0 < len(label) <= 80 and REQUIREMENTS.search(label):
                self.sections.append((label, []))
            self._strong = None
        elif tag in BLOCKS:
            self._emit("\n")

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        if self._heading is not None:
            self._heading.append(data)
            self._emit(data, section=False)
            return
        if self._strong is not None:
            self._strong.append(data)
        self._emit(data)


def _clean(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.replace("\r", "\n").split("\n")]
    joined = "\n".join(lines)
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    joined = re.sub(r"(?m)^- *$\n?", "", joined)
    return joined.strip()


def html_to_text(value: str | None, limit: int = MAX_DESCRIPTION) -> str | None:
    """Convert untrusted HTML to bounded plain text that keeps paragraphs and bullets."""
    if not value:
        return None
    parser = _TextParser(limit)
    parser.feed(value[: limit * 4])
    parser.close()
    return _clean("".join(parser.parts)) or None


def requirements_from_html(value: str | None, limit: int = MAX_DESCRIPTION) -> str | None:
    """Return text only from sections explicitly labelled as requirements."""
    if not value:
        return None
    parser = _TextParser(limit)
    parser.feed(value[: limit * 4])
    parser.close()
    found = [
        _clean("".join(parts))
        for label, parts in parser.sections
        if label and REQUIREMENTS.search(label)
    ]
    return "\n\n".join(text for text in found if text)[:limit] or None


def plain(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text[:limit] or None


def canonical_job_url(value: str, base: str | None = None) -> str:
    """Normalize a job URL: no fragment, no known tracking parameters, safe syntax."""
    parsed = urlsplit(urljoin(base, value.strip()) if base else value.strip())
    query = urlencode(
        [(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True)
         if not TRACKING.match(key)]
    )  # fmt: skip
    return source_url(urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, "")))


def _vocabulary(value: object, table: dict[str, str]) -> str:
    if isinstance(value, list):
        found = {_vocabulary(item, table) for item in value} - {"unknown"}
        return found.pop() if len(found) == 1 else "unknown"
    if not isinstance(value, str):
        return "unknown"
    key = " ".join(value.casefold().replace("_", " ").split())
    return table.get(key) or table.get(key.replace(" ", "_")) or "unknown"


def work_mode(value: object) -> str:
    return _vocabulary(value, WORK_MODES)


def employment_type(value: object) -> str:
    return _vocabulary(value, EMPLOYMENT_TYPES)


def timestamp(value: object) -> datetime | None:
    """Parse ISO 8601 text or epoch milliseconds; anything else is missing."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        seconds = value / 1000 if value > 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(seconds, UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


@dataclass
class NormalizedJob:
    canonical_url: str
    title: str
    extraction_method: str
    confidence: str
    source_job_id: str | None = None
    location_text: str | None = None
    work_mode: str = "unknown"
    employment_type: str = "unknown"
    department: str | None = None
    description_text: str | None = None
    requirements_text: str | None = None
    posted_at: datetime | None = None
    valid_through: datetime | None = None
    field_sources: dict[str, str] = field(default_factory=dict)
    shared_url: bool = False  # The URL is the listing page, not this posting's own page.

    def dedupe_key(self, platform: str | None) -> str:
        if self.source_job_id and platform:
            return f"{platform}:{self.source_job_id}"[:2100]
        if self.shared_url:
            return f"{self.canonical_url}#{self.source_job_id or self.fingerprint()}"[:2100]
        return self.canonical_url

    def fingerprint(self) -> str:
        title = " ".join(re.sub(r"[^\w]+", " ", self.title.casefold()).split())
        location = " ".join(re.sub(r"[^\w]+", " ", (self.location_text or "").casefold()).split())
        return hashlib.sha256(f"{title}|{location}".encode()).hexdigest()

    def content_hash(self) -> str:
        values = asdict(self)
        values.pop("field_sources")
        values.pop("shared_url")
        return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()


def build(
    *,
    url: str,
    title: object,
    method: str,
    confidence: str,
    base: str | None = None,
    sources: dict[str, str],
    **values: object,
) -> NormalizedJob | None:
    """Create a normalized job, or None when the title or URL is unusable."""
    clean_title = plain(title, MAX_TITLE)
    if not clean_title:
        return None
    try:
        canonical = canonical_job_url(url, base)
    except ValueError:
        return None
    job = NormalizedJob(
        canonical_url=canonical,
        title=clean_title,
        extraction_method=method,
        confidence=confidence,
    )
    for key, value in values.items():
        setattr(job, key, value)
    present = {key for key, value in asdict(job).items() if value not in (None, "unknown", {})}
    job.field_sources = {key: kind for key, kind in sources.items() if key in present}
    return job
