"""The Fact Check Tools adapter: parsing, the key in a header, caching, and the stage."""

import asyncio
import json

import httpx
import pytest

import pipeline.retrieve as retrieve
from pipeline.common.contracts import Claim, OutletType, Span
from pipeline.retrieve import fact_check_item, factcheck_api
from pipeline.retrieve.articles import Record
from pipeline.retrieve.cache import Cache, NoCache
from pipeline.retrieve.factcheck_api import find_reviews, parse
from pipeline.retrieve.tests.conftest import article_page
from pipeline.retrieve.tests.test_stage import analysis, run

ROUTE = "factchecktools.googleapis.com/v1alpha1/claims:search"
KEY = "test-key-not-real"
REVIEW_URL = "https://checker-unknown.example/verifica-pozzi"


def answer(*reviews: dict, claim: str = "Il governo vieterà i pozzi privati") -> bytes:
    return json.dumps({"claims": [{"text": claim, "claimReview": list(reviews)}]}).encode()


def review(url=REVIEW_URL, rating="Falso", **kw) -> dict:
    return {
        "publisher": {"name": "Checker", "site": "checker-unknown.example"},
        "url": url,
        "title": "Il governo non vieterà i pozzi",
        "reviewDate": "2026-11-12T08:00:00Z",
        "textualRating": rating,
        "languageCode": "it",
        **kw,
    }


def test_parse():
    [r] = parse(answer(review(), review(url="ftp://bad"), review(rating="")))
    assert r.claim == "Il governo vieterà i pozzi privati"
    assert (r.rating, r.publisher, r.language) == ("Falso", "Checker", "it")
    assert r.published_at == "2026-11-12T08:00:00+00:00"
    assert parse(b"{}") == [] and parse(b"not json") == [] and parse(b"[]") == []


def search(server, queries, cache=None):
    async def go():
        async with server.client() as client:
            return await find_reviews(client, cache or NoCache(), queries, KEY)

    return asyncio.run(go())


def test_the_key_goes_in_a_header_never_in_the_url(server):
    server.routes[ROUTE] = lambda request: httpx.Response(200, content=answer(review()))
    [r] = search(server, [("Il governo vieterà i pozzi privati", "it")])
    assert r.url == REVIEW_URL
    [request] = server.requests
    assert request.headers["X-Goog-Api-Key"] == KEY
    assert KEY not in str(request.url)
    assert request.url.params["languageCode"] == "it"
    assert request.url.params["query"] == "Il governo vieterà i pozzi privati"


def test_reviews_are_unique_capped_and_claims_first(server, monkeypatch):
    def route(request):
        q = request.url.params["query"]
        urls = [f"https://c.example/{q[:5]}-{i}" for i in range(4)] + [REVIEW_URL]
        return httpx.Response(200, content=answer(*[review(url=u) for u in urls]))

    server.routes[ROUTE] = route
    monkeypatch.setattr(factcheck_api, "MAX_REVIEWS", 6)
    found = search(server, [("prima query", "it"), ("seconda query", "it")])
    assert len(found) == 6
    assert [r.url for r in found][:5] == [f"https://c.example/prima-{i}" for i in range(4)] + [
        REVIEW_URL
    ]


def test_errors_give_no_reviews(server):
    for status in (400, 403, 429, 500):
        server.routes[ROUTE] = lambda request, s=status: httpx.Response(s, content=b"{}")
        assert search(server, [("q uno", "it")]) == []


def test_answers_are_cached_for_a_day(server, tmp_path):
    cache = Cache(tmp_path / "r.sqlite")
    server.routes[ROUTE] = lambda request: httpx.Response(200, content=answer(review()))
    first = search(server, [("Il governo vieterà i pozzi", "it")], cache)
    server.requests.clear()
    assert search(server, [("Il governo vieterà i pozzi", "it")], cache) == first
    assert server.requests == []


@pytest.fixture
def with_key(stage, monkeypatch):
    monkeypatch.setenv(factcheck_api.KEY_ENV, KEY)
    stage.routes[ROUTE] = lambda request: httpx.Response(200, content=answer(review()))
    return stage


def test_a_review_becomes_a_fact_check_item_and_its_outlet_a_fact_checker(with_key):
    with_key.pages[REVIEW_URL] = (
        200,
        # Long enough for Italian to outweigh the fixture's English filler: the item's language
        # is read from its text.
        article_page(
            "Verifica",
            "Il disegno di legge registra i pozzi, non li vieta, e il governo lo ha confermato "
            "ieri sera in una nota ufficiale pubblicata sul sito del ministero.",
        ),
    )
    a = analysis()
    a.claims = [
        Claim(
            id="cl1",
            text="Il governo vieterà i pozzi privati",
            span=Span(paragraph=0, start=0, end=1),
        )
    ]
    patch = run(a)
    [check] = [c for c in patch.context if c.fact_check is not None]
    assert check.retrieved_by == "fact_check_api"
    assert check.fact_check.model_dump() == {
        "claim": "Il governo vieterà i pozzi privati",
        "rating": "Falso",
        "publisher": "Checker",
    }
    assert check.text.startswith("Il governo vieterà i pozzi privati\n\nRating: Falso\n\n")
    assert "registra i pozzi, non li vieta" in check.text
    assert check.language == "it" and check.tracking_ids == ["G-AB12CD34EF"]
    assert check.published_at.isoformat() == "2026-11-12T08:00:00+00:00"
    profile = next(s for s in patch.sources if s.domain == "checker-unknown.example")
    assert profile.outlet_type == OutletType.fact_checker
    assert patch.detail == "2 related reports from 2 outlets, 1 fact-checks (2 feeds read)"
    # The claim goes first, in the document's language.
    first = with_key.requests[
        [r.url.host for r in with_key.requests].index("factchecktools.googleapis.com")
    ]
    assert first.url.params["query"] == "Il governo vieterà i pozzi privati"


def test_an_unreadable_review_page_still_gives_the_claim_and_rating(with_key):
    with_key.pages[REVIEW_URL] = (403, "")
    [check] = [c for c in run().context if c.fact_check is not None]
    assert check.text == "Il governo vieterà i pozzi privati\n\nRating: Falso"
    assert check.url == REVIEW_URL and check.tracking_ids == []


def test_no_key_means_no_api_call(stage, monkeypatch):
    monkeypatch.delenv(factcheck_api.KEY_ENV, raising=False)
    run()
    assert not any(r.url.host == "factchecktools.googleapis.com" for r in stage.requests)


def test_a_review_already_found_in_a_feed_is_not_doubled(with_key):
    with_key.routes[ROUTE] = lambda request: httpx.Response(
        200, content=answer(review(url="https://agency.example/meta"))
    )
    patch = run()
    assert [c.url for c in patch.context].count("https://agency.example/meta") == 1


def test_a_slow_api_is_dropped_at_its_budget(with_key, monkeypatch):
    async def slow(*args, **kwargs):
        await asyncio.sleep(5)
        return []

    monkeypatch.setattr(retrieve, "FACTCHECK_TIMEOUT_S", 0.3)
    monkeypatch.setattr(factcheck_api, "find_reviews", slow)
    patch = run()
    assert all(c.fact_check is None for c in patch.context) and len(patch.context) == 2


def test_a_fact_check_item_takes_its_language_from_its_text():
    """The API's `languageCode` is the publisher's tag: an English review filed under `it`
    is English, and a review with only a one-line claim keeps the tag."""
    italian = (
        "Il disegno di legge registra i pozzi privati e non li vieta: lo ha confermato il "
        "ministero in una nota ufficiale pubblicata ieri sera sul proprio sito."
    )
    english = (
        "The bill registers private wells and does not ban them, the ministry confirmed in an "
        "official note published on its website late on Tuesday evening."
    )

    def item(language: str | None, body: str | None, claim: str = "Il governo vieterà i pozzi"):
        review = factcheck_api.Review(
            url=REVIEW_URL,
            title="Verifica",
            claim=claim,
            rating="Falso",
            publisher="Checker",
            publisher_site="checker-unknown.example",
            published_at=None,
            language=language,
        )
        page = (
            Record(url=REVIEW_URL, title="Verifica", text=body, published_at=None, language=None)
            if body
            else None
        )
        return fact_check_item("ctx1", review, page)

    assert item("it", italian).language == "it"
    assert item("it", english, claim="The government will ban private wells").language == "en"
    assert item("en", italian).language == "it"
    assert item("it-IT", None).language == "it"  # claim and rating alone: the tag, bare
    assert item(None, None, claim="12 345").language is None
