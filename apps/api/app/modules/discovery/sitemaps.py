from dataclasses import dataclass

from defusedxml import ElementTree


@dataclass(frozen=True)
class Sitemap:
    urls: list[str]
    nested: list[str]


def parse_sitemap(body: bytes, max_urls: int = 2000) -> Sitemap:
    try:
        root = ElementTree.fromstring(body)
    except (ElementTree.ParseError, ValueError):
        return Sitemap([], [])
    tag = root.tag.rsplit("}", 1)[-1].lower()
    values = [
        "".join(node.itertext()).strip()
        for node in root.iter()
        if node.tag.rsplit("}", 1)[-1].lower() == "loc"
    ][:max_urls]
    if tag == "sitemapindex":
        return Sitemap([], values)
    if tag == "urlset":
        return Sitemap(values, [])
    return Sitemap([], [])
