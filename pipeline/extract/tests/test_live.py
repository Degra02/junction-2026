"""Extract on the real web. Skipped unless RUN_LIVE=1 (CI must not depend on outside sites).

    RUN_LIVE=1 uv run pytest pipeline/extract/tests/test_live.py -v

Articles come from each outlet's own RSS feed at run time, so the tests do not rot as news moves.
"""

import asyncio
import os

import feedparser
import httpx
import pytest
from fastapi.testclient import TestClient

import pipeline.extract as extract
from pipeline.common.contracts import ExtractPatch, Input, InputKind, LanguageSupport
from pipeline.common.errors import StageError
from pipeline.common.fixtures import example_analysis
from pipeline.extract.fetch import USER_AGENT

pytestmark = pytest.mark.skipif(not os.environ.get("RUN_LIVE"), reason="set RUN_LIVE=1")

# (language, feed): outlets checked on Sat 14.11 to serve full articles to a plain HTTP client.
FEEDS = [
    ("it", "https://www.ansa.it/sito/ansait_rss.xml"),
    ("en", "https://feeds.bbci.co.uk/news/rss.xml"),
    ("en", "https://www.theguardian.com/world/rss"),
    ("de", "https://www.tagesschau.de/index~rss2.xml"),
    ("es", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada"),
    ("nl", "https://feeds.nos.nl/nosnieuwsalgemeen"),
    ("pl", "https://tvn24.pl/najnowsze.xml"),
    ("ru", "https://meduza.io/rss/all"),
    ("uk", "https://www.pravda.com.ua/rss/"),
    ("fi", "https://yle.fi/rss/uutiset/paauutiset"),
    (
        "ar",
        "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4bd4-9d80-a84db769f779/73d0e1b4-532f-45ef-b135-bfdff8b8cab9",
    ),
    ("en", "https://fullfact.org/feed/"),  # a fact-checker
]


def feed_links(url: str, limit: int = 4) -> list[str]:
    response = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=15, follow_redirects=True)
    return [entry.link for entry in feedparser.parse(response.content).entries[:limit]]


def run_url(url: str) -> ExtractPatch:
    analysis = example_analysis()
    analysis.input = Input(kind=InputKind.url, value=url)
    return asyncio.run(extract.run(analysis))


@pytest.mark.parametrize(("code", "feed"), FEEDS, ids=[f"{c}-{f.split('/')[2]}" for c, f in FEEDS])
def test_real_article(code, feed):
    """The newest article of the feed that is readable (some items are videos or live pages)."""
    errors = []
    for link in feed_links(feed):
        try:
            patch = run_url(link)
        except StageError as e:
            errors.append(str(e))
            continue
        doc = patch.document
        assert doc.url and doc.outlet
        assert doc.title
        assert len(doc.paragraphs) >= 2
        assert sum(map(len, doc.paragraphs)) >= 500, "full text, not a teaser"
        assert doc.published_at is not None
        assert patch.language is not None
        assert patch.language.code == code
        assert patch.language.confidence > 0.9
        assert patch.language.support == LanguageSupport.supported
        return
    pytest.fail(f"no readable article in the first items: {errors}")


def test_paywalled_article_asks_for_the_text():
    links = [link for link in feed_links("https://www.spiegel.de/schlagzeilen/index.rss", 20)]
    for link in links:
        try:
            run_url(link)
        except StageError as e:
            if "subscribers" in str(e):
                return
    pytest.skip("no SPIEGEL+ article in the feed right now")


def test_http_link_is_followed_to_https():
    link = feed_links("https://www.theguardian.com/world/rss", 1)[0]
    patch = run_url(link.replace("https://", "http://", 1))
    assert patch.document.url is not None and patch.document.url.startswith("https://")


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("https://www.bbc.com/news/this-page-does-not-exist-0000", "not found"),
        ("https://arxiv.org/pdf/1706.03762", "not a web page"),
        (
            "https://www.bbc.com/news",
            "could not find an article",
        ),  # a section front, not an article
        ("http://169.254.169.254/latest/meta-data/", "public website"),  # cloud metadata address
        ("https://no-such-host.invalid/article", "could not be found"),
    ],
)
def test_unreadable_links_give_a_plain_reason(url, reason):
    with pytest.raises(StageError, match=reason):
        run_url(url)


def test_url_through_the_worker_endpoint():
    from worker.app import app

    link = feed_links("https://www.ansa.it/sito/ansait_rss.xml", 1)[0]
    analysis = example_analysis()
    analysis.input = Input(kind=InputKind.url, value=link)
    with TestClient(app) as client:  # runs the worker's startup, which imports every stage
        response = client.post("/stages/extract", json=analysis.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    patch = ExtractPatch.model_validate(response.json())
    assert patch.document.outlet == "ansa.it"
    assert patch.language is not None and patch.language.code == "it"
