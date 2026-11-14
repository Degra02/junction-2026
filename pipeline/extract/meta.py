"""Page metadata that the article text does not carry.

- Tracking IDs (Google Analytics, Tag Manager, AdSense): two unrelated-looking sites with the same
  ID are likely run by the same operator. Input for the infrastructure signal.
- ClaimReview: the structured verdict most fact-checkers embed in their pages (JSON-LD). Reading it
  from the page gives the same data as Google's Fact Check API, without a key.
- Precise publication time, canonical URL, page language, outbound links.
"""

import json
import re
from dataclasses import dataclass, field

import lxml.html

from pipeline.extract.urls import outlet_host

_UA = re.compile(r"\bUA-\d{4,10}-\d{1,4}\b")
_GA4 = re.compile(r"""(?:id=|['"])(G-[A-Z0-9]{8,12})(?=['"&])""")
_GTM = re.compile(r"\bGTM-[A-Z0-9]{4,9}\b")
_ADSENSE = re.compile(r"\b(?:ca-)?pub-(\d{10,20})\b")

_TIME_META = (
    "article:published_time",
    "og:published_time",
    "datePublished",
    "pubdate",
    "publishdate",
    "date",
)
_MAX_LINKS = 300


@dataclass
class ClaimReview:
    claim_reviewed: str | None
    rating: str | None  # the checker's own words, e.g. "False", "Misleading"
    rating_value: float | None
    best_rating: float | None
    worst_rating: float | None
    reviewer: str | None  # the fact-checking organisation
    claimant: str | None  # who made the claim, when stated
    url: str | None
    date_published: str | None
    language: str | None


@dataclass
class PageMeta:
    canonical_url: str | None = None
    # The headline the outlet shares on social media; unlike <title>, no " - Section - Site" suffix.
    og_title: str | None = None
    site_name: str | None = None
    html_lang: str | None = None
    # As written in the page, usually ISO 8601 with time.
    published_time: str | None = None
    tracking_ids: dict[str, list[str]] = field(default_factory=dict)
    outbound_links: list[str] = field(default_factory=list)
    jsonld_types: list[str] = field(default_factory=list)
    claim_reviews: list[ClaimReview] = field(default_factory=list)


def tracking_ids(html: str) -> dict[str, list[str]]:
    """Analytics and ad IDs found anywhere in the HTML; empty keys are left out."""
    found = {
        "ga_ua": sorted(set(_UA.findall(html))),
        "ga4": sorted(set(_GA4.findall(html))),
        "gtm": sorted(set(_GTM.findall(html))),
        "adsense": sorted({f"pub-{n}" for n in _ADSENSE.findall(html)}),
    }
    return {k: v for k, v in found.items() if v}


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _types(node: dict) -> list[str]:
    return [t for t in _as_list(node.get("@type")) if isinstance(t, str)]


def _name(value) -> str | None:
    """`author`/`publisher` can be a string, an object with `name`, or a list of either."""
    for item in _as_list(value):
        if isinstance(item, str) and item.strip():
            return item.strip()
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            return item["name"].strip()
    return None


def _number(value) -> float | None:
    try:
        return float(value)
    except TypeError, ValueError:
        return None


def _walk(node):
    """Yield every JSON object in a JSON-LD document, including those nested in @graph."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _claim_review(node: dict) -> ClaimReview:
    rating = node.get("reviewRating") if isinstance(node.get("reviewRating"), dict) else {}
    item = node.get("itemReviewed") if isinstance(node.get("itemReviewed"), dict) else {}
    language = node.get("inLanguage")
    return ClaimReview(
        claim_reviewed=node.get("claimReviewed")
        if isinstance(node.get("claimReviewed"), str)
        else None,
        rating=rating.get("alternateName") or rating.get("name"),
        rating_value=_number(rating.get("ratingValue")),
        best_rating=_number(rating.get("bestRating")),
        worst_rating=_number(rating.get("worstRating")),
        reviewer=_name(node.get("author")),
        claimant=_name(item.get("author")),
        url=node.get("url") if isinstance(node.get("url"), str) else None,
        date_published=node.get("datePublished")
        if isinstance(node.get("datePublished"), str)
        else None,
        language=language if isinstance(language, str) else _name(language),
    )


def _jsonld_documents(doc) -> list:
    out = []
    for script in doc.xpath('//script[@type="application/ld+json"]'):
        raw = (script.text or "").strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw, strict=False))
        except json.JSONDecodeError:
            continue  # broken JSON-LD is common; skip it rather than guess
    return out


def page_meta(html: str, page_url: str | None = None) -> PageMeta:
    """Parse metadata from raw HTML. Never raises on malformed pages; missing fields stay None."""
    meta = PageMeta(tracking_ids=tracking_ids(html))
    try:
        doc = lxml.html.fromstring(html)
    except lxml.etree.ParserError, ValueError:
        return meta

    meta.html_lang = (doc.get("lang") or "").strip() or None
    canonical = doc.xpath('//link[@rel="canonical"]/@href')
    meta.canonical_url = canonical[0].strip() if canonical else None

    named: dict[str, str] = {}
    for tag in doc.xpath("//meta[@content]"):
        key = tag.get("property") or tag.get("name") or tag.get("itemprop")
        if key and key not in named:
            named[key] = tag.get("content").strip()
    meta.site_name = named.get("og:site_name") or None
    meta.og_title = named.get("og:title") or None
    meta.canonical_url = meta.canonical_url or named.get("og:url") or None

    documents = _jsonld_documents(doc)
    nodes = [n for d in documents for n in _walk(d)]
    meta.jsonld_types = sorted({t for n in nodes for t in _types(n)})
    meta.claim_reviews = [_claim_review(n) for n in nodes if "ClaimReview" in _types(n)]

    published = next((named[k] for k in _TIME_META if named.get(k)), None)
    if not published:
        published = next(
            (n["datePublished"] for n in nodes if isinstance(n.get("datePublished"), str)),
            None,
        )
    meta.published_time = published

    own_host = outlet_host(page_url) if page_url else None
    links: list[str] = []
    seen: set[str] = set()
    for href in doc.xpath("//a/@href"):
        href = href.strip()
        if not href.startswith(("http://", "https://")) or href in seen:
            continue
        if own_host and outlet_host(href) == own_host:
            continue
        seen.add(href)
        links.append(href)
        if len(links) >= _MAX_LINKS:
            break
    meta.outbound_links = links
    return meta
