import asyncio

import httpx
import pytest

from pipeline.common.errors import StageError
from pipeline.extract.fetch import FetchFailed, Page, ensure_html, fetch_page, html_text, new_client

HTML = {"content-type": "text/html; charset=utf-8"}


def allow_all(url: str) -> None:
    pass


def block(fragment: str):
    def guard(url: str) -> None:
        if fragment in url:
            raise StageError("The link does not point to a public website")

    return guard


def fetch(handler, url="https://news.example/a", guard=allow_all, **kwargs) -> Page:
    async def go():
        async with new_client(httpx.MockTransport(handler)) as client:
            return await fetch_page(url, client, guard=guard, **kwargs)

    return asyncio.run(go())


def test_follows_redirects_and_checks_every_hop():
    checked = []

    def handler(request):
        if request.url.path == "/a":
            return httpx.Response(301, headers={"location": "/b"})  # relative
        if request.url.path == "/b":
            return httpx.Response(302, headers={"location": "https://cdn.example/c"})
        return httpx.Response(200, headers=HTML, text="<html>ok</html>")

    page = fetch(handler, guard=checked.append)
    assert page.url == "https://cdn.example/c"
    assert page.status == 200
    assert checked == ["https://news.example/a", "https://news.example/b", "https://cdn.example/c"]


def test_redirect_to_private_address_is_refused_before_it_is_requested():
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})

    with pytest.raises(FetchFailed, match="public website"):
        fetch(handler, guard=block("169.254.169.254"))
    assert requested == ["https://news.example/a"]


def test_redirect_loop_stops():
    def handler(request):
        return httpx.Response(302, headers={"location": "/loop"})

    with pytest.raises(FetchFailed, match="too many"):
        fetch(handler)


def test_redirect_without_location():
    with pytest.raises(FetchFailed, match="without a destination"):
        fetch(lambda request: httpx.Response(302))


def test_timeout_and_network_errors_become_plain_reasons():
    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    def down(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(FetchFailed, match="too long"):
        fetch(slow)
    with pytest.raises(FetchFailed, match="could not be reached"):
        fetch(down)


def test_body_is_cut_at_the_size_limit():
    page = fetch(lambda request: httpx.Response(200, headers=HTML, content=b"x" * 10), max_bytes=4)
    assert (page.body, page.truncated) == (b"xxxx", True)


def _page(status=200, content_type="text/html", body=b"<html><p>hi</p></html>") -> Page:
    return Page(url="https://news.example/a", status=status, content_type=content_type,
                body=body, truncated=False)  # fmt: skip


@pytest.mark.parametrize(
    ("page", "reason"),
    [
        (_page(status=402), "subscription"),
        (_page(status=403), "refused"),
        (_page(status=429), "refused"),
        (_page(status=404), "not found"),
        (_page(status=500), "error \\(HTTP 500\\)"),
        (_page(content_type="application/pdf"), "not a web page \\(application/pdf\\)"),
        (_page(body=b"  "), "empty"),
    ],
)
def test_ensure_html_rejects_unreadable_pages(page, reason):
    with pytest.raises(FetchFailed, match=reason):
        ensure_html(page)


def test_ensure_html_accepts_html_and_missing_content_type():
    ensure_html(_page())
    ensure_html(_page(content_type="application/xhtml+xml; charset=utf-8"))
    ensure_html(_page(content_type=""))


def test_html_text_reads_the_page_charset():
    body = '<html><head><meta charset="iso-8859-1"></head><body>Città</body></html>'
    assert "Città" in html_text(_page(body=body.encode("latin-1")))
