"""Adapters `x`, `reddit`, `bluesky`, `mastodon`, `telegram`: public posts that repeat the
document's wording (SPEC phase 2, "social-media repeated phrasing").

What is searched: the document's distinctive phrases (`phrases.distinctive_phrases`), verbatim.
- Bluesky has a public search API (`api.bsky.app`, `searchPosts`): free, returns whole posts.
- X, Reddit, Telegram and Mastodon have no search without an account, so the phrase goes to
  Oxylabs web search (D7) restricted to those sites; each result is then read from the platform's
  own public endpoint by `pipeline.extract.social`. Without `OXYLABS_TOKEN` only Bluesky is
  searched.
A post enters the context only if its text really repeats one of the phrases (search engines
loosen quoted queries), once per account, at most `PER_PLATFORM` per platform and `MAX_POSTS` in
all. Posts about the same topic in other words are not collected: a post is not a news report,
and `story` keeps every post out of the coverage that claims and tone are compared with.

What the signals see: `outlet` is the platform's domain (`x.com`, `reddit.com`), `author` the
account, `retrieved_by` the platform, `title` names the account for people, `text` is the post,
`published_at` its exact time. Copy detection counts one copy per account on a platform, so many
accounts posting the same text are many copies, not one site.

`SOCIAL_SEARCH=0` turns the adapters off. Search answers and posts are cached (each Oxylabs
search costs credit). The whole lane has one budget and never fails the stage.
"""

import asyncio
import json
import logging
import os
from collections import Counter
from dataclasses import asdict
from datetime import timedelta
from urllib.parse import quote

import httpx

from pipeline.common import net
from pipeline.common.contracts import ContextItem
from pipeline.common.errors import StageError
from pipeline.extract import scraper, social
from pipeline.extract.document import published_utc
from pipeline.extract.fetch import FetchFailed
from pipeline.extract.social import Post, PostRef
from pipeline.extract.urls import outlet_host
from pipeline.retrieve.cache import Cache, NoCache
from pipeline.retrieve.phrases import contains
from pipeline.retrieve.web import Web

log = logging.getLogger(__name__)

TIMEOUT_S = 45.0  # searches and reads together; runs beside the feeds and the article reads
SEARCH_TIMEOUT_S = 30.0
SEARCH_PHRASES = 2  # per analysis, on each search (each Oxylabs search costs credit)
BLUESKY_RESULTS = 25
WEB_RESULTS = 10  # the instant endpoint's maximum
MAX_READS = 16  # posts read from the platforms per analysis
# Per platform: no more can be kept than PER_PLATFORM, and a refused Reddit read costs credit.
READS_PER_PLATFORM = 6
PER_PLATFORM = 5
MAX_POSTS = 12
MIN_CHARS = 40  # shorter posts cannot hold a ten-word phrase anyway
SEARCH_MAX_AGE = timedelta(hours=6)
POST_MAX_AGE = timedelta(days=1)
# The sites the web search is restricted to (Bluesky is searched directly).
SEARCH_SITES = ("x.com", "twitter.com", "reddit.com", "t.me", "mastodon.social")
BLUESKY_SEARCH = "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts"
ADAPTERS = frozenset(social.PLATFORMS)  # the `retrieved_by` values of this module
_NS_SEARCH = "social_search"
_NS_POST = "social_post"


def enabled() -> bool:
    return os.environ.get("SOCIAL_SEARCH") != "0"


def parse_bluesky_search(body: bytes) -> list[Post]:
    try:
        entries = json.loads(body).get("posts") or []
    except ValueError, AttributeError:
        return []
    posts = []
    for entry in entries if isinstance(entries, list) else []:
        try:
            posts.append(social.bluesky_post(entry))
        except KeyError, TypeError, AttributeError, IndexError:
            continue
    return posts


async def bluesky_search(web: Web, cache: Cache | NoCache, phrase: str) -> list[Post]:
    """Bluesky posts that match the quoted phrase, newest first."""
    cached = cache.get(_NS_SEARCH, f"bluesky:{phrase}", SEARCH_MAX_AGE)
    if cached is not None:
        return [Post(**post) for post in cached]
    query = quote(f'"{phrase}"', safe="")
    url = f"{BLUESKY_SEARCH}?q={query}&limit={BLUESKY_RESULTS}&sort=latest"
    try:
        page = await web.get(url)
    except FetchFailed as e:
        log.info("Bluesky search: %s", e.reason)
        return []
    if page.status != 200:
        log.info("Bluesky search answered HTTP %s", page.status)
        return []
    posts = parse_bluesky_search(page.body)
    cache.put(_NS_SEARCH, f"bluesky:{phrase}", [asdict(post) for post in posts])
    return posts


def parse_web_search(body: bytes) -> list[PostRef]:
    """The posts among the result links of an Oxylabs instant-search answer."""
    try:
        entries = json.loads(body).get("data") or []
    except ValueError, AttributeError:
        return []
    refs: dict[str, PostRef] = {}
    for entry in entries if isinstance(entries, list) else []:
        url = entry.get("url") if isinstance(entry, dict) else None
        ref = social.post_ref(url) if isinstance(url, str) else None
        if ref is not None:
            refs.setdefault(ref.url, ref)
    return list(refs.values())


async def web_search(client: httpx.AsyncClient, cache: Cache | NoCache, phrase: str) -> list[str]:
    """Addresses of posts on SEARCH_SITES that a web search finds for the quoted phrase."""
    if not scraper.enabled():
        return []
    cached = cache.get(_NS_SEARCH, f"web:{phrase}", SEARCH_MAX_AGE)
    if cached is not None:
        return list(cached)
    sites = " OR ".join(f"site:{site}" for site in SEARCH_SITES)
    try:
        await asyncio.to_thread(net.assert_public_url, scraper.API_URL)
        response = await scraper.call(
            client,
            "POST",
            "/search/instant",
            body={"query": f'"{phrase}" ({sites})', "limit": WEB_RESULTS},
            timeout_s=SEARCH_TIMEOUT_S,
        )
    except StageError, FetchFailed:
        return []
    except httpx.HTTPError as e:
        log.info("Oxylabs social search unreachable (%s)", type(e).__name__)
        return []
    if response.status_code != 200:
        log.warning("Oxylabs social search answered HTTP %s", response.status_code)
        return []
    urls = [ref.url for ref in parse_web_search(response.content)]
    cache.put(_NS_SEARCH, f"web:{phrase}", urls)
    return urls


async def _read(web: Web, cache: Cache | NoCache, url: str) -> Post | None:
    ref = social.post_ref(url)
    if ref is None:
        return None
    cached = cache.get(_NS_POST, ref.url, POST_MAX_AGE)
    if cached is not None:
        return Post(**cached) if cached else None
    try:
        post = await social.read_post(ref, web.get, client=web.client)
    except FetchFailed as e:
        log.info("post not readable (%s)", e.reason)
        # A deleted or private post stays so; a refusal or an outage may be over tomorrow.
        if e.reason == social.NOT_AVAILABLE:
            cache.put(_NS_POST, ref.url, {})
        return None
    cache.put(_NS_POST, ref.url, asdict(post))
    return post


def select(posts: list[Post], phrases: list[str], own_url: str | None) -> list[Post]:
    """The posts that repeat a phrase: not the document itself, one per account, at most
    PER_PLATFORM per platform and MAX_POSTS in all, earliest first (who said it first matters
    for timing)."""
    own = social.post_ref(own_url) if own_url else None
    chosen: list[Post] = []
    seen: set[str] = set()
    accounts: set[tuple[str, str]] = set()
    per_platform: Counter[str] = Counter()
    for post in sorted(posts, key=lambda p: str(published_utc(p.published_at) or "9")):
        ref = social.post_ref(post.url)
        key = ref.url if ref else post.url
        text = social.post_text(post)
        if key in seen or (own is not None and key == own.url) or len(text) < MIN_CHARS:
            continue
        if not any(contains(text, phrase) for phrase in phrases):
            continue
        account = (post.platform, (post.author or key).casefold())
        if account in accounts or per_platform[post.platform] >= PER_PLATFORM:
            continue
        seen.add(key)
        accounts.add(account)
        per_platform[post.platform] += 1
        chosen.append(post)
        if len(chosen) == MAX_POSTS:
            break
    return chosen


def _to_read(urls: list[str]) -> list[str]:
    """The addresses worth reading: each post once, within the per-platform and overall caps."""
    chosen: list[str] = []
    per_platform: Counter[str] = Counter()
    for url in dict.fromkeys(urls):
        ref = social.post_ref(url)
        if ref is None or per_platform[ref.platform] >= READS_PER_PLATFORM:
            continue
        per_platform[ref.platform] += 1
        chosen.append(url)
    return chosen[:MAX_READS]


async def _find(web: Web, cache: Cache | NoCache, phrases: list[str], own_url: str | None):
    searched = phrases[:SEARCH_PHRASES]
    found = await asyncio.gather(
        *(bluesky_search(web, cache, phrase) for phrase in searched),
        *(web_search(web.client, cache, phrase) for phrase in searched),
        return_exceptions=True,
    )
    posts: list[Post] = []
    urls: list[str] = []
    for result in found:
        if isinstance(result, BaseException):
            log.warning("social search failed", exc_info=result)
            continue
        for entry in result:
            (posts if isinstance(entry, Post) else urls).append(entry)
    urls = _to_read(urls)
    read = await asyncio.gather(*(_read(web, cache, url) for url in urls), return_exceptions=True)
    posts += [post for post in read if isinstance(post, Post)]
    return select(posts, phrases, own_url)


async def find_posts(
    web: Web, cache: Cache | NoCache, phrases: list[str], own_url: str | None = None
) -> list[Post]:
    """Public posts that repeat one of `phrases`. Never raises: a platform that is down or slow
    is skipped, and at TIMEOUT_S the lane gives up with nothing."""
    if not phrases or not enabled():
        return []
    try:
        async with asyncio.timeout(TIMEOUT_S):
            return await _find(web, cache, phrases, own_url)
    except TimeoutError:
        log.warning("social search timed out")
    except Exception:
        log.warning("social search failed", exc_info=True)
    return []


def post_item(item_id: str, post: Post) -> ContextItem:
    """A post as a context item: `author` is the account (copies are counted per account), the
    title names it for people, the text is everything the author wrote."""
    where = f" in {post.community}" if post.platform == social.REDDIT and post.community else ""
    who = f" by {post.author}" if post.author else ""
    return ContextItem(
        id=item_id,
        url=post.url,
        outlet=outlet_host(post.url) or None,
        published_at=published_utc(post.published_at),
        title=f"Post{who} on {social.PLATFORMS[post.platform]}{where}",
        author=post.author,
        text=social.post_text(post),
        language=post.language,
        retrieved_by=post.platform,
        tracking_ids=[],
    )
