"""Exact-phrase search: phrase choice, GDELT and Oxylabs adapters, and the stage."""

import asyncio
import itertools
import json
import time

import httpx
import pytest

import pipeline.retrieve as retrieve
from pipeline.common.contracts import Document
from pipeline.extract import scraper
from pipeline.retrieve import gdelt, oxylabs
from pipeline.retrieve.cache import NoCache
from pipeline.retrieve.phrases import WORDS, contains, distinctive_phrases
from pipeline.retrieve.tests.conftest import AGENCY_ITEM, article_page
from pipeline.retrieve.tests.test_stage import analysis, run

GDELT_ROUTE = "api.gdeltproject.org/api/v2/doc/doc"
OXY_ROUTE = "api-aistudio.oxylabs.io/search/instant"
OWN = (
    "Il ministero ha confermato che dal primo gennaio 2027 i pozzi privati dovranno essere "
    "registrati presso gli uffici regionali competenti entro novanta giorni."
)
QUOTED = (
    "«Nessuno vieterà i pozzi, chiederemo soltanto una semplice registrazione online» ha detto."
)
COPY = "https://copy-site.example/2026/11/pozzi"


def doc(*paragraphs: str) -> Document:
    return Document(paragraphs=list(paragraphs), outbound_links=[], tracking_ids=[])


def test_phrases_are_verbatim_windows_from_the_middle_of_own_words_first():
    phrases = distinctive_phrases(doc(QUOTED + " " + OWN, "Troppo corta."))
    assert len(phrases) == 2
    first = phrases[0].split()
    assert len(first) == WORDS
    assert phrases[0] in " ".join(OWN.replace(",", "").replace(".", "").split())
    assert "Il" not in first[:1]  # the window sits in the middle, not at the opening
    assert "registrazione" in phrases[1]  # the quoted sentence only as a fallback


def test_phrases_drop_punctuation_keep_apostrophes_and_are_capped():
    text = " ".join(
        f"Frase numero {i}, con l'Ucraina e il pre-1997: parole diverse ancora {i} qui."
        for i in range(5)
    )
    phrases = distinctive_phrases(doc(text))
    assert len(phrases) == 3
    assert all("," not in p and ":" not in p for p in phrases)
    assert any("l'Ucraina" in p or "pre-1997" in p for p in phrases)
    assert distinctive_phrases(None) == [] and distinctive_phrases(doc("Breve.")) == []


GDELT_ANSWER = {
    "articles": [
        {
            "url": COPY,
            "title": "Pozzi  privati",
            "seendate": "20261113T081500Z",
            "domain": "copy-site.example",
            "language": "Italian",
        },
        {"url": "ftp://nope", "title": "x"},
        {
            "url": "https://other.example/a",
            "title": "Other",
            "seendate": "bad",
            "language": "Klingon",
        },
    ]
}


def test_gdelt_parse():
    copy, other = gdelt.parse(json.dumps(GDELT_ANSWER).encode())
    assert (copy.url, copy.title, copy.language, copy.outlet) == (
        COPY,
        "Pozzi privati",
        "it",
        "copy-site.example",
    )
    assert copy.published_at == "2026-11-13T08:15:00+00:00"
    assert (other.language, other.published_at) == ("", None)
    assert gdelt.parse(b"Please limit requests") == [] and gdelt.parse(b"{}") == []


def test_gdelt_requests_are_paced_and_quoted(server, monkeypatch):
    monkeypatch.setattr(gdelt, "INTERVAL_S", 0.3)
    monkeypatch.setattr(gdelt, "_last_call", 0.0)
    times: list[float] = []

    def route(request):
        times.append(time.monotonic())
        return httpx.Response(200, content=json.dumps(GDELT_ANSWER).encode())

    server.routes[GDELT_ROUTE] = route

    async def go():
        async with server.client() as client:
            return await asyncio.gather(
                *(gdelt.search(client, NoCache(), f"frase {i}") for i in range(3))
            )

    results = asyncio.run(go())
    assert all(len(r) == 2 for r in results)
    assert all(b - a >= 0.29 for a, b in itertools.pairwise(times))
    assert {r.url.params["query"] for r in server.requests} == {
        '"frase 0"',
        '"frase 1"',
        '"frase 2"',
    }


def test_gdelt_rate_limit_gives_nothing(server, monkeypatch):
    monkeypatch.setattr(gdelt, "INTERVAL_S", 0.0)
    server.routes[GDELT_ROUTE] = lambda request: httpx.Response(
        429, content=b"Please limit requests"
    )

    async def go():
        async with server.client() as client:
            return await gdelt.search(client, NoCache(), "una frase")

    assert asyncio.run(go()) == []


def oxy_answer(*urls: str) -> bytes:
    data = [
        {"url": u, "title": f"T {u}", "description": "snippet", "content": None, "source": "x"}
        for u in urls
    ]
    return json.dumps({"run_id": "r1", "status": "completed", "data": data}).encode()


def test_oxylabs_parse_drops_search_engine_links():
    items = oxylabs.parse(
        oxy_answer(COPY, "https://www.google.com/search?q=x", "https://youtube.com/w"), "it"
    )
    assert [(i.url, i.language, i.summary) for i in items] == [(COPY, "it", "snippet")]
    assert oxylabs.parse(b"{}") == [] and oxylabs.parse(b"[]") == [] and oxylabs.parse(b"x") == []


def test_oxylabs_sends_the_key_in_a_header_and_a_quoted_query(server, monkeypatch):
    monkeypatch.setenv(scraper.TOKEN_ENV, "test-key-not-real")
    server.routes[OXY_ROUTE] = lambda request: httpx.Response(200, content=oxy_answer(COPY))

    async def go():
        async with server.client() as client:
            return await oxylabs.search(client, NoCache(), "una frase esatta")

    [item] = asyncio.run(go())
    assert item.url == COPY
    [request] = server.requests
    assert request.headers["x-api-key"] == "test-key-not-real"
    assert "test-key-not-real" not in str(request.url)
    assert json.loads(request.content) == {"query": '"una frase esatta"', "limit": 10}


@pytest.mark.parametrize("status", [401, 402, 429, 500])
def test_oxylabs_errors_give_no_results(server, monkeypatch, status):
    monkeypatch.setenv(scraper.TOKEN_ENV, "test-key-not-real")
    server.routes[OXY_ROUTE] = lambda request: httpx.Response(status, content=b"{}")

    async def go():
        async with server.client() as client:
            return await oxylabs.news_search(client, NoCache(), "una query", "it")

    assert asyncio.run(go()) == []


def test_oxylabs_is_off_without_a_key(monkeypatch):
    monkeypatch.delenv(scraper.TOKEN_ENV, raising=False)
    assert not scraper.enabled()


@pytest.fixture
def phrase_stage(stage, monkeypatch):
    monkeypatch.setattr(gdelt, "INTERVAL_S", 0.0)
    a = analysis()
    a.document.paragraphs = [OWN]
    stage.routes[GDELT_ROUTE] = lambda request: httpx.Response(
        200, content=json.dumps(GDELT_ANSWER).encode()
    )
    stage.pages[COPY] = (200, article_page("Pozzi privati", OWN))
    return stage, a


def test_a_copy_found_by_exact_phrase_enters_the_context(phrase_stage):
    _, a = phrase_stage
    patch = run(a)
    [copy] = [c for c in patch.context if c.retrieved_by == "gdelt"]
    assert copy.url == COPY and copy.outlet == "copy-site.example"
    assert OWN in copy.text  # read in full, not the search snippet
    assert "copy-site.example" in [s.domain for s in patch.sources]
    assert "(1 by exact phrase)" in patch.detail


def test_oxylabs_hits_join_when_the_key_is_set(phrase_stage, monkeypatch):
    stage, a = phrase_stage
    monkeypatch.setenv(scraper.TOKEN_ENV, "test-key-not-real")
    monkeypatch.setattr(scraper, "enabled", lambda: True)
    old = "https://old-mirror.example/2025/03/pozzi"
    stage.routes[OXY_ROUTE] = lambda request: httpx.Response(200, content=oxy_answer(old))
    stage.pages[old] = (200, article_page("Pozzi", OWN))
    patch = run(a)
    by = {c.url: c.retrieved_by for c in patch.context}
    assert by[old] == "oxylabs" and by[COPY] == "gdelt"


def test_the_same_article_from_a_phrase_search_and_a_feed_counts_once(phrase_stage):
    stage, a = phrase_stage
    answer = {"articles": [{"url": AGENCY_ITEM, "title": "x", "language": "Italian"}]}
    stage.routes[GDELT_ROUTE] = lambda request: httpx.Response(
        200, content=json.dumps(answer).encode()
    )
    patch = run(a)
    assert [c.url for c in patch.context].count(AGENCY_ITEM) == 1
    # The agency page does not repeat the phrase, so it counts as the feed hit it also was.
    assert next(c for c in patch.context if c.url == AGENCY_ITEM).retrieved_by == "feeds"
    stage.pages[AGENCY_ITEM] = (200, article_page("Pozzi", OWN))
    patch = run(a)
    assert next(c for c in patch.context if c.url == AGENCY_ITEM).retrieved_by == "gdelt"


def test_a_slow_phrase_search_is_dropped_at_its_budget(phrase_stage, monkeypatch):
    _, a = phrase_stage
    monkeypatch.setattr(retrieve, "PHRASES_TIMEOUT_S", 0.3)
    original = gdelt.search

    async def slow(*args, **kwargs):
        await asyncio.sleep(5)
        return await original(*args, **kwargs)

    monkeypatch.setattr(gdelt, "search", slow)
    patch = run(a)
    assert all(c.retrieved_by == "feeds" for c in patch.context)


def test_topic_search_finds_coverage_outside_the_feeds(phrase_stage, monkeypatch):
    stage, a = phrase_stage
    monkeypatch.setenv(scraper.TOKEN_ENV, "test-key-not-real")
    monkeypatch.setattr(scraper, "enabled", lambda: True)
    other = "https://regional-paper.example/2026/11/meta-garante"

    def route(request):
        query = json.loads(request.content)["query"]
        if query.startswith('"'):  # exact-phrase searches: nothing
            return httpx.Response(200, content=oxy_answer())
        body = json.loads(oxy_answer(other, "https://unrelated.example/sport"))
        body["data"][0]["title"] = "Il Garante privacy multa Meta"
        body["data"][1]["title"] = "Calcio, vince la Roma"
        return httpx.Response(200, content=json.dumps(body).encode())

    stage.routes[OXY_ROUTE] = route
    stage.pages[other] = (200, article_page("Multa a Meta", "Il Garante privacy ha multato Meta."))
    patch = run(a)
    by = {c.url: c.retrieved_by for c in patch.context}
    assert by[other] == "oxylabs_news"  # matched on its words, like a feed item
    assert "https://unrelated.example/sport" not in by
    assert "(1 from news search)" in patch.detail


def test_contains_ignores_case_spacing_and_punctuation():
    assert contains(
        "Il ministero: «pozzi privati, registrati» entro gennaio.", "pozzi privati registrati"
    )
    assert not contains("I pozzi privati non saranno registrati", "pozzi privati registrati")
    assert not contains("pozzi privatissimi registrati", "pozzi privati registrati")


def test_a_phrase_hit_that_does_not_repeat_the_phrase_is_dropped(phrase_stage):
    stage, a = phrase_stage
    stage.pages[COPY] = (
        200,
        article_page("Altro", "Un articolo su un altro argomento del giorno."),
    )
    patch = run(a)
    assert all(c.url != COPY for c in patch.context)


def test_reference_and_social_sites_are_not_coverage():
    links = [
        "https://en.wikipedia.org/wiki/X", "https://www.facebook.com/p", "https://x.com/u/1",
        "https://mobile.twitter.com/u", "https://www.google.it/search", "https://box.com/news",
    ]  # fmt: skip
    assert [i.url for i in oxylabs.parse(oxy_answer(*links))] == ["https://box.com/news"]
