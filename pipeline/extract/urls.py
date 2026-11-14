"""URL helpers.

`canonical_url` gives one spelling per article, so the same story found by two sources (or with
different tracking parameters) is stored and counted once.
"""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query parameters that only track the click, never change the article.
_TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "yclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ocid",
    "cmpid",
    "smid",
    "smtyp",
    "ref",
    "ref_src",
    "ito",
    "guccounter",
    "_ga",
}
_TRACKING_PREFIXES = ("utm_", "at_")


def _is_tracking(param: str) -> bool:
    p = param.lower()
    return p in _TRACKING_PARAMS or p.startswith(_TRACKING_PREFIXES)


def canonical_url(url: str) -> str:
    """Normalise an http(s) URL for deduplication.

    https, lower-case host without `www.`, no fragment, no tracking parameters, remaining
    parameters sorted, no trailing slash. Raises ValueError for anything that is not http(s).
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"not an http(s) URL: {url!r}")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError(f"URL without host: {url!r}")
    host = host.removeprefix("www.")
    port = parts.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if len(path) > 1:
        path = path.rstrip("/")
    query = sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _is_tracking(k)
    )
    return urlunsplit(("https", netloc, path, urlencode(query), ""))


def outlet_host(url: str) -> str:
    """Host of the outlet, lower-case, without `www.` (subdomains kept: `fr.example.com`)."""
    host = (urlsplit(url.strip()).hostname or "").lower().rstrip(".")
    return host.removeprefix("www.")
