import re
import unicodedata

from app.core.urls import source_url


def name_candidate(name: str | None) -> str | None:
    """Return one low-confidence guess without performing DNS or network access."""
    if not name:
        return None
    normalized = unicodedata.normalize("NFKC", name).strip().casefold()
    if not re.fullmatch(r"[a-z0-9]+(?:[ -][a-z0-9]+)*", normalized):
        return None
    label = re.sub(r"[ -]+", "", normalized)
    if not label or len(label) > 63 or label.startswith("-") or label.endswith("-"):
        return None
    try:
        return source_url(f"https://{label}.com/")
    except ValueError:
        return None
