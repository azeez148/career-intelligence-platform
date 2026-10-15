"""Catalog-free phrase matching: normalization and contiguous token-sequence lookup.

Separators between word characters are equivalent to spaces ("Node.js" ~ "node js",
"full-time" ~ "full time"), while symbols that carry meaning stay part of a token
("c++", "c#", ".net"). No plural, stemming, or synonym inference is performed.
"""

import re
import unicodedata
from collections import defaultdict

INNER_SEPARATOR = re.compile(r"(?<=\w)[.\-_/'’](?=\w)")
TOKEN = re.compile(r"\.?\w+[+#]*")
MAX_TEXT = 400_000


def tokens(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    text = unicodedata.normalize("NFKC", value[:MAX_TEXT]).casefold()
    return tuple(TOKEN.findall(INNER_SEPARATOR.sub(" ", text)))


class TextIndex:
    """Positions of each token so phrase lookups avoid rescanning long descriptions."""

    def __init__(self, value: str | None) -> None:
        self.tokens = tokens(value)
        self.positions: dict[str, list[int]] = defaultdict(list)
        for index, token in enumerate(self.tokens):
            self.positions[token].append(index)

    def __bool__(self) -> bool:
        return bool(self.tokens)

    def contains(self, phrase: tuple[str, ...]) -> bool:
        if not phrase:
            return False
        for start in self.positions.get(phrase[0], ()):
            if self.tokens[start : start + len(phrase)] == phrase:
                return True
        return False


class JobText:
    """Searchable job fields in explanation order."""

    FIELDS = ("title", "requirements", "description", "department")

    def __init__(
        self,
        title: str,
        department: str | None,
        description: str | None,
        requirements: str | None,
    ) -> None:
        self.indexes = {
            "title": TextIndex(title),
            "requirements": TextIndex(requirements),
            "description": TextIndex(description),
            "department": TextIndex(department),
        }

    @property
    def has_body(self) -> bool:
        return bool(self.indexes["requirements"] or self.indexes["description"])

    def find(self, value: str) -> str | None:
        """Return the first field containing the phrase, or None."""
        phrase = tokens(value)
        for field in self.FIELDS:
            if self.indexes[field].contains(phrase):
                return field
        return None
