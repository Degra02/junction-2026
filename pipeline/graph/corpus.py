"""What stored analyses hold about outlets: every article they read, the outlet profiles and the
hyperlinks of the analysed documents.

An article is the analysed document (when it came from a URL: pasted text has no verifiable
origin) or a context item. The same URL read by several analyses is one article. Social media
posts are left out: a platform is not an outlet.

Three kinds of host need their own rule, each learnt from a false tie in the eval records
(plans/source-graph.md, section 3):

- *social* hosts (`t.me`, `ok.ru`...) carry other people's posts and are never a node;
- *hosting platforms* (`blogspot.com`, `wordpress.com`...) hold unrelated sites under one
  registrable domain, so each subdomain is its own operator, and an analytics or ad ID found
  there belongs to the platform;
- *official* sites (governments, armed forces) publish statements that are meant to be
  republished, like a news agency.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from pipeline.common.contracts import Analysis, InputKind, OutletType
from pipeline.extract.social import is_post
from pipeline.retrieve.sources import registrable
from pipeline.signals.text import normalize_domain

SOCIAL = frozenset(
    {
        "t.me",
        "telegram.me",
        "telegra.ph",
        "tgstat.com",
        "ok.ru",
        "vk.com",
        "max.ru",
        "dzen.ru",
        "facebook.com",
        "instagram.com",
        "threads.net",
        "x.com",
        "twitter.com",
        "bsky.app",
        "reddit.com",
        "youtube.com",
        "tiktok.com",
        "linkedin.com",
    }
)
HOSTING = (
    "blogspot.com",
    "wordpress.com",
    "substack.com",
    "medium.com",
    "tumblr.com",
    "livejournal.com",
    "over-blog.com",
    "canalblog.com",
    "github.io",
    "wixsite.com",
    "weebly.com",
)
# Labels of government and military hosts: `gov.uk`, `diplomatie.gouv.fr`, `lamoncloa.gob.es`,
# `pm.gc.ca`, `war.gov`. Official sites outside the pattern (`elysee.fr`) need an outlet type.
_OFFICIAL_LABELS = frozenset({"gov", "gouv", "gob", "govt", "gc", "mil"})


def hosted(domain: str) -> bool:
    """Whether `domain` is a site on a hosting platform."""
    return any(domain.endswith(f".{platform}") for platform in HOSTING)


def operator(domain: str) -> str:
    """Who runs the site, as far as the name tells: the registrable domain
    (`deutsch.news-pravda.com` -> `news-pravda.com`), or the full host on a hosting platform."""
    if hosted(domain):
        return domain
    return registrable(domain) or domain


def social(domain: str) -> bool:
    return (registrable(domain) or domain) in SOCIAL


def official(domain: str) -> bool:
    return not _OFFICIAL_LABELS.isdisjoint(domain.split("."))


@dataclass
class Article:
    url: str
    outlet: str
    title: str | None
    text: str
    published_at: datetime | None
    # Whether it was the document of an analysis (URL input), not only a context item.
    analysed: bool = False
    fact_check: bool = False
    tracking_ids: set[str] = field(default_factory=set)
    # IDs of the analyses that read it.
    analyses: set[str] = field(default_factory=set)


@dataclass
class Outlet:
    domain: str
    outlet_type: OutletType | None = None
    country: str | None = None
    known_network: str | None = None


@dataclass
class Corpus:
    articles: list[Article]
    # Every outlet of an article, with what `retrieve` knew about it.
    outlets: dict[str, Outlet]
    # (linking outlet, linked outlet) -> analyses whose document holds the link. Both are
    # outlets of the corpus with different operators.
    links: dict[tuple[str, str], set[str]]
    analyses: int


def collect(analyses: Iterable[Analysis]) -> Corpus:
    articles: dict[str, Article] = {}
    profiles: dict[str, Outlet] = {}
    outbound: dict[tuple[str, str], set[str]] = {}
    count = 0

    def read(url: str, outlet: str | None, title: str | None, text: str) -> Article | None:
        domain = normalize_domain(outlet) or normalize_domain(url)
        if not domain or social(domain) or not text.strip():
            return None
        return articles.setdefault(url, Article(url, domain, title, text, None))

    for analysis in analyses:
        count += 1
        key = str(analysis.id)
        for source in analysis.sources:
            domain = normalize_domain(source.domain)
            if not domain:
                continue
            known = profiles.setdefault(domain, Outlet(domain))
            known.outlet_type = known.outlet_type or source.outlet_type
            known.country = known.country or source.country
            known.known_network = known.known_network or source.known_network
        document = analysis.document
        from_url = analysis.input.value if analysis.input.kind == InputKind.url else None
        url = document.url or from_url if document else None
        if document and url and document.outlet:
            article = read(url, document.outlet, document.title, "\n".join(document.paragraphs))
            if article:
                article.analysed = True
                article.published_at = article.published_at or document.published_at
                article.tracking_ids.update(document.tracking_ids)
                article.analyses.add(key)
                for link in document.outbound_links:
                    target = normalize_domain(link)
                    if target and operator(target) != operator(article.outlet):
                        outbound.setdefault((article.outlet, target), set()).add(key)
        for item in analysis.context:
            if is_post(item.url, item.retrieved_by):
                continue
            article = read(item.url, item.outlet, item.title, item.text)
            if article:
                article.fact_check = article.fact_check or item.fact_check is not None
                article.published_at = article.published_at or item.published_at
                article.tracking_ids.update(item.tracking_ids)
                article.analyses.add(key)

    found = list(articles.values())
    outlets = {a.outlet: profiles.get(a.outlet, Outlet(a.outlet)) for a in found}
    links = {pair: seen for pair, seen in outbound.items() if pair[1] in outlets}
    return Corpus(articles=found, outlets=outlets, links=links, analyses=count)
