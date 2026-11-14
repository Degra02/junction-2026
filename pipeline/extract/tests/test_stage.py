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
from pipeline.extract import scraper
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
