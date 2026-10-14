from urllib.parse import urlsplit


def platform_for(url: str, html: str = "") -> str | None:
    host = (urlsplit(url).hostname or "").lower()
    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io", "boards-api.greenhouse.io"}:
        return "greenhouse"
    if host in {"jobs.lever.co", "api.lever.co"}:
        return "lever"
    if host.endswith(".myworkdayjobs.com") or host == "myworkdayjobs.com":
        return "workday"
    lowered = html[:200_000].lower()
    if "boards.greenhouse.io" in lowered or "job-boards.greenhouse.io" in lowered:
        return "greenhouse"
    if "jobs.lever.co" in lowered:
        return "lever"
    if "myworkdayjobs.com" in lowered:
        return "workday"
    return None
