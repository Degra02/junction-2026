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
from pipeline.common.contracts import ExtractPatch, Input, InputKind
from pipeline.common.errors import StageError
from pipeline.common.fixtures import example_analysis
from pipeline.extract import scraper
from pipeline.extract.fetch import USER_AGENT
from pipeline.extract.language import support_for

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
        assert patch.language.support == support_for(code)
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


# Scraping fallback (needs OXYLABS_TOKEN, or OXYLABS_USERNAME and OXYLABS_PASSWORD; costs credit).

needs_oxylabs = pytest.mark.skipif(not scraper.enabled(), reason="set the Oxylabs credentials")


@needs_oxylabs
def test_bot_checked_site_is_read_through_the_scraper():
    """France24 answers plain HTTP with 403 (Sat 14.11)."""
    link = feed_links("https://www.france24.com/fr/rss", 1)[0]
    patch = run_url(link)
    assert patch.document.outlet == "france24.com"
    assert sum(map(len, patch.document.paragraphs)) >= 300
    assert patch.language is not None and patch.language.code == "fr"


@needs_oxylabs
def test_site_behind_a_javascript_challenge_gives_an_article_or_a_plain_reason():
    """TASS serves a JavaScript challenge to plain clients and to headless browsers."""
    link = feed_links("https://tass.ru/rss/v2.xml", 1)[0]
    try:
        patch = run_url(link)
    except StageError as e:
        assert "paste its text" in str(e) or "refused" in str(e)
    else:
        assert patch.language is not None and patch.language.code == "ru"


# --- social media posts ----------------------------------------------------------------------
# Posts that have been public for years (X, Telegram, Reddit) or are picked at run time
# (Bluesky, Mastodon), so the tests do not rot.


def _post(url: str):
    return run_url(url).document


def test_an_x_post():
    document = _post("https://twitter.com/jack/status/20?s=20")
    assert document.paragraphs == ["just setting up my twttr"]
    assert document.author == "@jack" and document.outlet is None
    assert document.url == "https://x.com/jack/status/20"
    assert document.published_at.date().isoformat() == "2006-03-21"


def test_an_x_post_made_after_2010_has_its_exact_time():
    document = _post("https://x.com/jack/status/801270269184647168")
    assert document.published_at.isoformat().startswith("2016-11-23T03:44:53")
    assert "just setting up my twttr" in document.paragraphs[0]


def test_a_deleted_x_post_gives_a_plain_reason():
    with pytest.raises(StageError, match="private, deleted or only visible after logging in"):
        _post("https://x.com/jack/status/1")


def test_a_telegram_post():
    document = _post("https://t.me/s/durov/342")
    assert document.url == "https://t.me/durov/342" and document.author == "Pavel Durov"
    assert len(document.paragraphs) >= 5 and document.published_at.year == 2024
    with pytest.raises(StageError, match="private, deleted"):
        _post("https://t.me/durov/99999999")


def test_a_bluesky_post():
    feed = httpx.get(
        "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed",
        params={"actor": "bsky.app", "limit": 30, "filter": "posts_no_replies"},
        timeout=20,
    ).json()["feed"]
    post = next(
        f["post"]
        for f in feed
        if f["post"]["author"]["handle"] == "bsky.app" and f["post"]["record"].get("text")
    )
    document = _post(f"https://bsky.app/profile/bsky.app/post/{post['uri'].rsplit('/', 1)[1]}")
    assert "\n\n".join(document.paragraphs).split() == post["record"]["text"].split()
    assert document.author == "@bsky.app" and document.published_at is not None


def test_a_mastodon_post():
    statuses = httpx.get(
        "https://mastodon.social/api/v1/timelines/tag/news",
        params={"limit": 30},
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    ).json()
    status = next(s for s in statuses if s["url"].startswith("https://mastodon.social/@"))
    document = _post(status["url"])
    assert document.paragraphs and document.author.endswith("@mastodon.social")
    assert document.url == status["url"] and document.outlet is None


def test_a_reddit_post():
    # Reddit turns many addresses away (HTTP 429); with the Oxylabs key the feed is still read.
    try:
        document = _post("https://old.reddit.com/r/cs50/comments/y7dleo/whatever_the_slug/")
    except StageError as e:
        if scraper.enabled() or "did not answer" not in str(e):
            raise
        pytest.skip("Reddit refused this address and no OXYLABS_TOKEN is set")
    assert document.title == "CS50 Python problem set 2 Just setting up my twttr"
    assert document.author == "u/Mav3r1ck-13" and document.published_at.year == 2022
    assert document.url.startswith("https://www.reddit.com/r/cs50/comments/y7dleo/")
    assert document.paragraphs[0].startswith("I am new to coding")
