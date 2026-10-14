import unicodedata


def display_text(value: str) -> str:
    return " ".join(value.split())


def comparison_key(value: str) -> str:
    return display_text(unicodedata.normalize("NFKC", value)).casefold()
