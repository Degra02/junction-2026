"""Guard for fetching URLs that come from users or from web pages.

The worker runs inside the deployment's private network. A URL such as `http://worker:8001/`
or `http://169.254.169.254/` must never be fetched on a user's behalf (server-side request
forgery). The API rejects the obvious cases at submission; only the fetcher can check what a
host name resolves to and where redirects lead.
"""

import ipaddress
import socket
from urllib.parse import urlsplit

from pipeline.common.errors import StageError


def assert_public_url(url: str) -> None:
    """Raise `StageError` unless `url` is http(s) and its host resolves only to public addresses.

    Call it before fetching the analysed URL and again for every redirect hop: fetch with
    redirects disabled and check each `Location` before following it.
    """
    parts = urlsplit(url)
    host = parts.hostname
    if parts.scheme not in ("http", "https") or not host:
        raise StageError("Only http(s) links can be analysed")
    try:
        resolved = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise StageError("The link's site could not be found") from e
    for *_, sockaddr in resolved:
        if not ipaddress.ip_address(sockaddr[0].split("%")[0]).is_global:
            raise StageError("The link does not point to a public website")
