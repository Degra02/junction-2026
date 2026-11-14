"""The stage function as the worker calls it, offline: fake HTTP responses, permissive URL guard."""

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import pipeline.extract as extract
from pipeline.common import net
from pipeline.common.contracts import ExtractPatch, Input, InputKind, LanguageSupport
from pipeline.common.errors import StageError
from pipeline.common.fixtures import example_analysis
from pipeline.extract import scraper, social
from pipeline.extract.fetch import new_client

BODY = [
    "The city council approved the new tram line on Tuesday after a debate that lasted six hours.",
    "Opponents said the cost estimate had doubled since the first proposal two years ago.",
    "The mayor said construction would start in spring and the first section would open in 2028.",
]


def article_page(extra_head: str = "") -> str:
    paragraphs = "".join(f"<p>{p}</p>" for p in BODY).replace(
        "city council", '<a href="https://council.example/minutes">city council</a>'
    )
    return f"""<html lang="en"><head><title>Tram line approved | City Paper</title>
<meta property="og:title" content="Tram line approved">
<meta property="article:published_time" content="2026-11-10T18:05:00+01:00">
<meta name="author" content="Jane Doe">
<script>gtag('config', 'G-AB12CD34EF');</script>{extra_head}
</head><body><nav>Home Sport</nav><article><h1>Tram line approved</h1>{paragraphs}
</article></body></html>"""


def analysis(kind: InputKind, value: str):
    a = example_analysis()
    a.input = Input(kind=kind, value=value)
    return a


@pytest.fixture
def web(monkeypatch):
    """Serve `pages[url] = (status, headers, body)`; the URL guard allows every host."""
    pages: dict[str, tuple[int, dict, str]] = {}

    def handler(request):
        status, headers, body = pages[str(request.url)]
        return httpx.Response(status, headers=headers, text=body)

    monkeypatch.setattr(net, "assert_public_url", lambda url: None)
    monkeypatch.setattr(scraper, "enabled", lambda: False)  # scraper tests: test_scraper.py
    monkeypatch.delenv(scraper.TOKEN_ENV, raising=False)
    monkeypatch.setattr(extract, "new_client", lambda: new_client(httpx.MockTransport(handler)))
    return pages


def test_text_input():
    patch = asyncio.run(extract.run(analysis(InputKind.text, "\n\n".join(BODY))))
    assert isinstance(patch, ExtractPatch)
    assert patch.document.paragraphs == BODY
    assert patch.document.url is None
    assert patch.language is not None
    assert patch.language.code == "en"
    assert patch.language.support == LanguageSupport.evaluated


def test_empty_text_input_is_refused():
    with pytest.raises(StageError, match="no text"):
        asyncio.run(extract.run(analysis(InputKind.text, " \n\n ")))


def test_url_input(web):
    web["https://www.citypaper.example/tram"] = (301, {"location": "/2026/tram"}, "")
    web["https://www.citypaper.example/2026/tram"] = (
        200,
        {"content-type": "text/html"},
        article_page(),
    )
    patch = asyncio.run(extract.run(analysis(InputKind.url, "https://www.citypaper.example/tram")))
    doc = patch.document
    assert doc.url == "https://www.citypaper.example/2026/tram"  # final address after the redirect
    assert doc.outlet == "citypaper.example"
    assert doc.title == "Tram line approved"
    assert doc.author == "Jane Doe"
    assert (
        doc.published_at is not None and doc.published_at.isoformat() == "2026-11-10T17:05:00+00:00"
    )
    assert doc.paragraphs == BODY
    assert doc.tracking_ids == ["G-AB12CD34EF"]
    assert doc.outbound_links == ["https://council.example/minutes"]
    assert patch.language is not None and patch.language.code == "en"
    # What the worker sends back must round-trip through the contract.
    ExtractPatch.model_validate(json.loads(patch.model_dump_json()))


def test_paywalled_url_asks_for_the_text(web):
    paywall = (
        '<script type="application/ld+json">'
        '{"@type": "NewsArticle", "isAccessibleForFree": false}</script>'
    )
    web["https://news.example/s"] = (200, {"content-type": "text/html"}, article_page(paywall))
    with pytest.raises(StageError, match="subscribers"):
        asyncio.run(extract.run(analysis(InputKind.url, "https://news.example/s")))


@pytest.mark.parametrize(
    ("status", "headers", "body", "reason"),
    [
        (
            200,
            {"content-type": "text/html"},
            "<html><body><nav>Home</nav></body></html>",
            "paste its text",
        ),
        (403, {"content-type": "text/html"}, "denied", "refused"),
        (200, {"content-type": "application/pdf"}, "%PDF", "not a web page"),
    ],
)
def test_unreadable_url_gives_a_plain_reason(web, status, headers, body, reason):
    web["https://news.example/x"] = (status, headers, body)
    with pytest.raises(StageError, match=reason):
        asyncio.run(extract.run(analysis(InputKind.url, "https://news.example/x")))


def test_private_url_is_refused():
    # The real guard: no network needed, these addresses resolve locally.
    for url in ["http://127.0.0.1:8001/health", "http://localhost/", "http://10.0.0.5/admin"]:
        with pytest.raises(StageError, match="public website"):
            asyncio.run(extract.run(analysis(InputKind.url, url)))


def test_through_the_worker_endpoint():
    from worker.app import app

    body = analysis(InputKind.text, "\n\n".join(BODY)).model_dump(mode="json")
    response = TestClient(app).post("/stages/extract", json=body)
    assert response.status_code == 200, response.text
    patch = ExtractPatch.model_validate(response.json())
    assert patch.document.paragraphs == BODY
    assert patch.language is not None and patch.language.code == "en"


# --- social media posts ----------------------------------------------------------------------

POST = (
    "The council secretly sold the harbour to a foreign fund last night, insiders say. "
    "Nobody was told, and the papers were signed behind closed doors."
)
X_URL = "https://twitter.com/Some_User/status/1855000000000000000?s=20"


def x_answer(text: str) -> str:
    return json.dumps(
        {
            "url": "https://twitter.com/Some_User/status/1855000000000000000",
            "author_url": "https://twitter.com/Some_User",
            "html": f'<blockquote class="twitter-tweet"><p lang="en" dir="ltr">{text}</p>&mdash; '
            'Some User (@Some_User) <a href="https://twitter.com/Some_User/status/'
            '1855000000000000000">November 8, 2024</a></blockquote>',
        }
    )


def test_a_post_url_is_read_from_the_platform_not_as_a_page(web):
    endpoint = social.post_ref(X_URL).endpoint
    web[endpoint] = (200, {"content-type": "application/json"}, x_answer(POST))
    patch = asyncio.run(extract.run(analysis(InputKind.url, X_URL)))
    document = patch.document
    assert document.paragraphs == [POST]
    assert document.url == "https://x.com/Some_User/status/1855000000000000000"
    assert document.author == "@Some_User" and document.outlet is None
    assert document.published_at.isoformat() == "2024-11-08T21:30:38.890000+00:00"
    assert patch.language.code == "en"
    # Only the public endpoint was asked: the post's own page (a JavaScript app) never is.
    assert list(web) == [endpoint]


def test_a_deleted_post_gives_a_plain_reason_without_the_address(web):
    web[social.post_ref(X_URL).endpoint] = (404, {}, "{}")
    with pytest.raises(StageError) as e:
        asyncio.run(extract.run(analysis(InputKind.url, X_URL)))
    assert str(e.value) == (
        "The post is private, deleted or only visible after logging in. Paste its text instead"
    )
    assert "Some_User" not in str(e.value) and "http" not in str(e.value)


def test_a_post_without_words_gives_a_plain_reason(web):
    web[social.post_ref(X_URL).endpoint] = (200, {}, x_answer(""))
    with pytest.raises(StageError, match="The post has no text to analyse"):
        asyncio.run(extract.run(analysis(InputKind.url, X_URL)))


def test_a_private_address_behind_a_post_link_is_refused(web, monkeypatch):
    def guard(url):
        raise StageError("The link does not point to a public website")

    monkeypatch.setattr(net, "assert_public_url", guard)
    with pytest.raises(StageError, match="public website") as e:
        asyncio.run(extract.run(analysis(InputKind.url, "https://10.0.0.5/@admin/1234567")))
    assert "Paste" not in str(e.value)


def test_a_page_whose_address_only_looks_like_a_post_is_read_as_an_article(web):
    # Mastodon runs on any host, so `/@name/digits` is tried as a post first; this site is a
    # newspaper, its API path answers 404, and the page is then read like any article.
    url = "https://paper.example/@desk/20261110"
    web["https://paper.example/api/v1/statuses/20261110"] = (404, {}, "Not found")
    web[url] = (200, {"content-type": "text/html; charset=utf-8"}, article_page())
    patch = asyncio.run(extract.run(analysis(InputKind.url, url)))
    assert patch.document.paragraphs == BODY and patch.document.outlet == "paper.example"


def test_a_mastodon_post_on_any_host(web):
    url = "https://m.example/@alice/117616784931828866"
    status = {
        "url": url,
        "created_at": "2026-11-14T20:55:11.491Z",
        "language": "en",
        "content": f"<p>{POST}</p>",
        "account": {"acct": "alice"},
    }
    web["https://m.example/api/v1/statuses/117616784931828866"] = (200, {}, json.dumps(status))
    document = asyncio.run(extract.run(analysis(InputKind.url, url))).document
    assert document.paragraphs == [POST] and document.author == "@alice@m.example"
    assert document.outlet is None


def test_a_post_through_the_worker_endpoint(web):
    from worker.app import app

    web[social.post_ref(X_URL).endpoint] = (200, {}, x_answer(POST))
    body = analysis(InputKind.url, X_URL).model_dump(mode="json")
    response = TestClient(app).post("/stages/extract", json=body)
    assert response.status_code == 200
    assert ExtractPatch.model_validate(response.json()).document.paragraphs == [POST]
