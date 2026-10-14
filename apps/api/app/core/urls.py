"""Pure source URL input validation. This does not authorize network access."""

import re
from urllib.parse import quote, unquote, urlsplit, urlunsplit

_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_LOCAL_SUFFIXES = {
    "localhost",
    "local",
    "internal",
    "invalid",
    "test",
    "example",
    "home",
    "lan",
    "arpa",
    "onion",
}


def source_url(value: str) -> str:
    def invalid() -> ValueError:
        return ValueError("Enter an absolute HTTP(S) URL with a public DNS hostname")

    if not value or len(value) > 2048:
        raise invalid()
    if any(char.isspace() or ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
        raise invalid()
    if "\\" in value or "#" in value or re.search(r"%(?![0-9a-fA-F]{2})", value):
        raise invalid()
    decoded = unquote(value)
    if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in decoded) or "\\" in decoded:
        raise invalid()
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
            raise invalid()
        if "@" in parsed.netloc or "%" in parsed.netloc or parsed.netloc.endswith(":"):
            raise invalid()
        if parsed.port not in {None, 80 if parsed.scheme == "http" else 443}:
            raise invalid()
        host = parsed.hostname.removesuffix(".").encode("idna").decode("ascii").lower()
        host.encode("ascii").decode("idna")  # Validate pre-encoded IDNA labels as well.
        labels = host.split(".")
        if (
            len(host) > 253
            or len(labels) < 2
            or labels[-1] in _LOCAL_SUFFIXES
            or not re.search(r"[a-z]", labels[-1])
            or not all(_LABEL.fullmatch(label) for label in labels)
        ):
            raise invalid()
        # Numeric top-level labels include browser-interpreted IPv4/hex/octal variants.
        if re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)", labels[-1]):
            raise invalid()
        result = urlunsplit(
            (
                parsed.scheme,
                host,
                quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~"),
                quote(parsed.query, safe="/%?:@!$&'()*+,;=-._~"),
                "",
            )
        )
    except (ValueError, UnicodeError):
        raise invalid() from None
    if len(result) > 2048:
        raise invalid()
    return result
