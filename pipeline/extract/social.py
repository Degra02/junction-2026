"""Posts on social networks (X, Reddit, Bluesky, Mastodon, Telegram): recognise a post's address,
read the post, turn it into the `Document`. Shared with `retrieve`, which reads the posts it finds.

A post is not an article page: X and Reddit answer a plain client with a JavaScript app or a
refusal, so the article extractor finds nothing. Each platform has a public endpoint that returns
one post without logging in, and that is what is read here:
- X: the oEmbed API behind embedded posts (`publish.twitter.com/oembed`);
- Bluesky: the public AppView (`public.api.bsky.app`, `getPostThread`);
- Mastodon: the instance's own API (`/api/v1/statuses/{id}`);
- Telegram: the public embed of a channel post (`t.me/{channel}/{id}?embed=1`);
- Reddit: the post's Atom feed (`/comments/{id}/.rss`). Reddit turns datacenter addresses away,
  so a refused feed is fetched through Oxylabs (`scraper.scrape_raw`) when the key is set.
Only public posts are readable; a private, deleted or login-only post raises `FetchFailed` with a
plain reason. Nothing here logs in, and no account data beyond the public handle is kept.

`Document.outlet` stays empty for a post. The platform is not its publisher (the account is), and
the signals compare outlets by domain: with `x.com` as the outlet, every other post on X would
count as the document's own site and could never be a copy of it.
"""

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

import feedparser
import httpx
import lxml.html

from pipeline.common.contracts import Document
from pipeline.extract import scraper
from pipeline.extract.document import published_utc
from pipeline.extract.fetch import FetchFailed, Page
from pipeline.extract.text import paragraphs_from_text

X, REDDIT, BLUESKY, MASTODON, TELEGRAM = "x", "reddit", "bluesky", "mastodon", "telegram"
# Platform -> the name shown to users.
PLATFORMS = {
    X: "X",
    REDDIT: "Reddit",
    BLUESKY: "Bluesky",
    MASTODON: "Mastodon",
    TELEGRAM: "Telegram",
}
NOT_AVAILABLE = "The post is private, deleted or only visible after logging in"
NOT_READABLE = "We could not read that post"
NO_TEXT = "The post has no text to analyse"

_X_HOSTS = {"x.com", "twitter.com", "mobile.twitter.com", "mobile.x.com"}
_REDDIT_HOSTS = {"reddit.com", "old.reddit.com", "new.reddit.com", "np.reddit.com", "m.reddit.com"}
_TELEGRAM_HOSTS = {"t.me", "telegram.me"}
_X_PATH = re.compile(r"/(?:(?P<user>\w{1,15})|i(?:/web)?)/status(?:es)?/(?P<id>\d{1,20})(?:/|$)")
_REDDIT_PATH = re.compile(
    r"(?:/(?:r|u|user)/[^/]+)?/comments/(?P<id>[a-z0-9]{2,12})"
    r"(?:/[^/]*(?:/(?P<comment>[a-z0-9]{2,16}))?)?/?$"
)
_BLUESKY_PATH = re.compile(r"/profile/(?P<actor>[\w.:-]+)/post/(?P<rkey>[a-z0-9]{6,20})/?$")
_MASTODON_PATH = re.compile(
    r"/(?:@(?P<user>[\w.-]+)(?:@[\w.-]+)?|users/[\w.-]+/statuses)/(?P<id>\d{6,25})/?$"
)
_TELEGRAM_PATH = re.compile(r"/(?:s/)?(?P<channel>[A-Za-z]\w{3,31})/(?P<id>\d{1,12})/?$")
# X's first post IDs were a counter; since November 2010 an ID starts with its millisecond.
_SNOWFLAKE_MIN = 1 << 40
_SNOWFLAKE_EPOCH_MS = 1288834974657
_X_NOISE = re.compile(r"\s*(?:https?://t\.co/\w+|pic\.(?:twitter|x)\.com/\w+)")
_REDDIT_GONE = {"[removed]", "[deleted]", "[ removed by reddit ]"}

type Get = Callable[[str], Awaitable[Page]]


@dataclass(frozen=True)
class PostRef:
    """One post, from its address alone."""

    platform: str
    url: str  # normalised address: two links to the same post give the same `url`
    endpoint: str  # the public address the post is read from
    # False when only the shape of the address says "post": Mastodon runs on any host, so an
    # ordinary page may look like one; the caller then falls back to reading it as an article.
    certain: bool = True
    comment: str | None = None  # Reddit: the comment the link points at


@dataclass
class Post:
    platform: str
    url: str  # permalink
    author: str | None  # public handle, as the platform writes it: "@jack", "u/name"
    text: str  # the author's words; paragraphs separated by blank lines
    published_at: str | None  # ISO 8601
    title: str | None = None  # Reddit: the post's title
    community: str | None = None  # Reddit: "r/worldnews"
    language: str | None = None  # ISO 639-1, when the platform says
    links: list[str] = field(default_factory=list)


def post_ref(url: str) -> PostRef | None:
    """The post `url` points at, or None when it is not a post on a platform we read."""
    try:
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower().removeprefix("www.")
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not host:
        return None
    path = parts.path
    if host in _X_HOSTS and (m := _X_PATH.match(path)):
        link = f"https://x.com/{m['user'] or 'i'}/status/{m['id']}"
        oembed = f"https://publish.twitter.com/oembed?url={quote(link, safe='')}"
        return PostRef(X, link, oembed + "&omit_script=1&dnt=1&lang=en")
    if host in _REDDIT_HOSTS and (m := _REDDIT_PATH.match(path)):
        tail = f"/_/{m['comment']}" if m["comment"] else ""
        link = f"https://www.reddit.com/comments/{m['id']}{tail}"
        return PostRef(REDDIT, link, f"{link}/.rss?limit=1", comment=m["comment"])
    if host == "redd.it" and re.fullmatch(r"/[a-z0-9]{2,12}/?", path):
        link = f"https://www.reddit.com/comments/{path.strip('/')}"
        return PostRef(REDDIT, link, f"{link}/.rss?limit=1")
    if host == "bsky.app" and (m := _BLUESKY_PATH.match(path)):
        uri = f"at://{m['actor']}/app.bsky.feed.post/{m['rkey']}"
        return PostRef(
            BLUESKY,
            f"https://bsky.app/profile/{m['actor'].lower()}/post/{m['rkey']}",
            "https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread"
            f"?uri={quote(uri, safe='')}&depth=0&parentHeight=0",
        )
    if host in _TELEGRAM_HOSTS and (m := _TELEGRAM_PATH.match(path)):
        link = f"https://t.me/{m['channel']}/{m['id']}"
        return PostRef(TELEGRAM, link, f"{link}?embed=1&mode=tme")
    if m := _MASTODON_PATH.match(path):
        return PostRef(
            MASTODON,
            f"https://{host}{path.rstrip('/')}",
            f"https://{host}/api/v1/statuses/{m['id']}",
            certain=False,
        )
    return None


def is_post(url: str, retrieved_by: str = "") -> bool:
    """Whether a context item is a social media post: found by a social adapter, or at the
    address of a post on a known platform."""
    if retrieved_by in PLATFORMS:
        return True
    ref = post_ref(url)
    return ref is not None and ref.certain


def _fragment_text(fragment: str) -> tuple[str, list[str]]:
    """Plain text of an HTML fragment (paragraphs separated by blank lines) and its links."""
    root = lxml.html.fragment_fromstring(fragment, create_parent="div")
    for node in root.iter("br"):
        node.tail = "\n" + (node.tail or "")
    for node in root.iter("p", "blockquote", "li", "pre", "div"):
        node.tail = "\n\n" + (node.tail or "")
    links = [h for a in root.iter("a") if (h := a.get("href") or "").startswith("http")]
    lines = [" ".join(line.split()) for line in root.text_content().splitlines()]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text, list(dict.fromkeys(links))


def _language(code: object) -> str | None:
    """`en` from `en` or `en-GB`; None for X's `und`, `qme`... (no language)."""
    if not isinstance(code, str):
        return None
    primary = code.split("-")[0].lower()
    return primary if len(primary) == 2 and primary.isalpha() else None


def _x_time(post_id: int, date_text: str) -> str | None:
    if post_id >= _SNOWFLAKE_MIN:
        ms = (post_id >> 22) + _SNOWFLAKE_EPOCH_MS
        return datetime.fromtimestamp(ms / 1000, UTC).isoformat()
    try:
        return datetime.strptime(date_text.strip(), "%B %d, %Y").replace(tzinfo=UTC).isoformat()
    except ValueError:
        return None


def parse_x(body: bytes, ref: PostRef) -> Post:
    data = json.loads(body)
    root = lxml.html.fragment_fromstring(data["html"], create_parent="div")
    paragraph = root.find(".//p")
    if paragraph is None:
        raise ValueError("no post text in the oEmbed answer")
    text, links = _fragment_text(lxml.html.tostring(paragraph, encoding="unicode", with_tail=False))
    url = str(data.get("url") or ref.url)
    handle = urlsplit(str(data.get("author_url") or "")).path.strip("/")
    dates = [a.text_content() for a in root.iter("a") if "/status/" in (a.get("href") or "")]
    return Post(
        platform=X,
        url=url.replace("https://twitter.com/", "https://x.com/"),
        author=f"@{handle}" if handle else None,
        text=_X_NOISE.sub("", text).strip(),
        published_at=_x_time(int(ref.url.rsplit("/", 1)[1]), dates[-1] if dates else ""),
        language=_language(paragraph.get("lang")),
        links=links,
    )


def bluesky_post(post: dict) -> Post:
    """A post object of the Bluesky API (`getPostThread`, `searchPosts`)."""
    record = post["record"]
    handle = post["author"]["handle"]
    links = [
        feature["uri"]
        for facet in record.get("facets") or []
        for feature in facet.get("features") or []
        if isinstance(feature.get("uri"), str)
    ]
    external = (record.get("embed") or {}).get("external") or {}
    if isinstance(external.get("uri"), str):
        links.append(external["uri"])
    return Post(
        platform=BLUESKY,
        url=f"https://bsky.app/profile/{handle}/post/{post['uri'].rsplit('/', 1)[1]}",
        author=f"@{handle}",
        text=str(record.get("text") or "").replace("\r\n", "\n").strip(),
        published_at=record.get("createdAt"),
        language=_language((record.get("langs") or [None])[0]),
        links=[link for link in dict.fromkeys(links) if link.startswith("http")],
    )


def parse_bluesky(body: bytes, ref: PostRef) -> Post:
    return bluesky_post(json.loads(body)["thread"]["post"])


def parse_mastodon(body: bytes, ref: PostRef) -> Post:
    data = json.loads(body)
    data = data.get("reblog") or data  # a boost: the boosted post is the content
    text, links = _fragment_text(data["content"])
    acct = data["account"]["acct"]
    host = urlsplit(ref.url).hostname
    card = (data.get("card") or {}).get("url")
    return Post(
        platform=MASTODON,
        url=str(data.get("url") or ref.url),
        author=f"@{acct}" if "@" in acct else f"@{acct}@{host}",
        text=text,
        published_at=data.get("created_at"),
        language=_language(data.get("language")),
        links=list(dict.fromkeys(links + ([card] if isinstance(card, str) else []))),
    )


def _by_class(root, name: str) -> list:
    return root.xpath(f'//*[contains(concat(" ", normalize-space(@class), " "), " {name} ")]')


def parse_telegram(body: bytes, ref: PostRef) -> Post:
    root = lxml.html.fromstring(body.decode("utf-8", "replace"))
    blocks = _by_class(root, "js-message_text") or _by_class(root, "tgme_widget_message_text")
    if _by_class(root, "tgme_widget_message_error") or not blocks:
        raise FetchFailed(NOT_AVAILABLE)
    text, links = _fragment_text(lxml.html.tostring(blocks[0], encoding="unicode", with_tail=False))
    times = root.xpath("//time/@datetime")
    owner = _by_class(root, "tgme_widget_message_owner_name")
    name = " ".join(owner[0].text_content().split()) if owner else ""
    return Post(
        platform=TELEGRAM,
        url=ref.url,
        author=name or ref.url.split("/")[3],
        text=text,
        published_at=times[0] if times else None,
        community=ref.url.split("/")[3],
        links=links,
    )


def parse_reddit(body: bytes, ref: PostRef) -> Post:
    entries = feedparser.parse(body).entries
    wanted = f"t1_{ref.comment}" if ref.comment else "t3_"
    entry = next((e for e in entries if str(e.get("id", "")).startswith(wanted)), None)
    if entry is None:
        raise FetchFailed(NOT_AVAILABLE)
    content = entry.get("content") or [{}]
    root = lxml.html.fragment_fromstring(content[0].get("value") or "", create_parent="div")
    # The author's own text is the `md` block; a link post has none, only the linked address.
    own = _by_class(root, "md")
    text, _ = (
        _fragment_text(lxml.html.tostring(own[0], encoding="unicode", with_tail=False))
        if own
        else ("", [])
    )
    if text.casefold() in _REDDIT_GONE:
        raise FetchFailed(NOT_AVAILABLE)
    links = [
        href
        for a in root.iter("a")
        if (href := a.get("href") or "").startswith("http")
        and (a.text_content().strip() == "[link]" or (own and own[0] in a.iterancestors()))
    ]
    tags = entry.get("tags") or [{}]
    name = str(entry.get("author") or "").strip("/")
    return Post(
        platform=REDDIT,
        url=str(entry.get("link") or ref.url),
        author=name or None,
        text=text,
        published_at=entry.get("published") or entry.get("updated"),
        title=None if ref.comment else " ".join(str(entry.get("title") or "").split()) or None,
        community=tags[0].get("label") or None,
        links=[link for link in dict.fromkeys(links) if post_ref(link) != ref],
    )


_PARSERS = {
    X: parse_x,
    REDDIT: parse_reddit,
    BLUESKY: parse_bluesky,
    MASTODON: parse_mastodon,
    TELEGRAM: parse_telegram,
}
_REFUSED = {403, 429}
_GONE = {400, 401, 403, 404, 410}


async def read_post(ref: PostRef, get: Get, *, client: httpx.AsyncClient | None = None) -> Post:
    """The post behind `ref`. `get` fetches one address (and checks every redirect hop); `client`
    is reused for the Oxylabs fallback. Raises `FetchFailed` with a plain reason."""
    page = await get(ref.endpoint)
    if page.status in _REFUSED and ref.platform == REDDIT and scraper.enabled():
        page = await scraper.scrape_raw(ref.endpoint, client=client)
    if page.status in _GONE:
        raise FetchFailed(NOT_AVAILABLE)
    if page.status != 200:
        raise FetchFailed(f"{PLATFORMS[ref.platform]} did not answer (HTTP {page.status})")
    try:
        post = _PARSERS[ref.platform](page.body, ref)
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, lxml.etree.Error) as e:
        # Not the platform's format: a changed API, or (Mastodon) an ordinary page after all.
        raise FetchFailed(NOT_READABLE) from e
    post.text = post.text.replace("\r\n", "\n").strip()
    if not post.text and not post.title:
        raise FetchFailed(NO_TEXT)
    return post


def post_text(post: Post) -> str:
    """Everything the author wrote: a Reddit title is part of it."""
    return "\n\n".join(part for part in (post.title, post.text) if part)


def document_from_post(post: Post) -> Document:
    """The post as the analysed document. A Reddit link post has no body, so its title is the
    text; otherwise the title stays a title."""
    paragraphs = paragraphs_from_text(post.text)
    return Document(
        url=post.url,
        outlet=None,  # see the module docstring
        published_at=published_utc(post.published_at),
        title=post.title if paragraphs else None,
        author=post.author,
        paragraphs=paragraphs or paragraphs_from_text(post.title or ""),
        outbound_links=post.links,
        tracking_ids=[],
    )
