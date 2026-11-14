"""Which feed items cover the analysed story: shared content words with the queries and claims.

A deliberately simple lexical filter: feeds hold a few thousand recent items, and `story` judges
the survivors with embeddings afterwards. Words are case- and accent-folded and cut to a
6-character stem, so `migranti`/`migrants` or `Albania`/`albanese` meet. A query matches an item
in its language when at least `MIN_SHARED` of its words appear and they carry `MIN_SHARE` of the
query's weight (rare words weigh more).
"""

import math
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from pipeline.retrieve.feeds import FeedItem

MIN_SHARED = 2
SUMMARY_CHARS = 400
MIN_SHARE = 0.5
STEM = 6
_WORD = re.compile(r"\w+", re.UNICODE)
# Frequent function words of four letters or more in the languages we feed (it, en, es, fr, de,
# pt, nl); shorter words are dropped anyway.
_STOP_WORDS = """
    that this with from have will what when were been they their there about after into over
    more than also just said says such some only other which while would could should
    della dello delle degli dalla dalle nella nelle sulla sulle alla alle anche sono come
    dopo questo questa quella quello perche contro ancora essere stato stata tutti oggi
    para como pero esta este estos sobre entre desde hasta tras porque segun tambien
    dans pour avec sont cette sans sous entre selon apres avant aussi leur leurs plus
    nach eine einen einer eines nicht sich uber werden wird auch oder sind beim noch
    mais pela pelo esta seus suas como sobre depois ainda
    voor door niet maar zijn deze naar over
"""
_STOP = frozenset(_STOP_WORDS.split())


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def terms(text: str) -> frozenset[str]:
    """Content-word stems of `text`: 4+ letters, or tokens with a digit (years, figures)."""
    out = set()
    for word in _WORD.findall(_fold(text)):
        if word.isdigit() and len(word) < 2:
            continue
        if not any(c.isdigit() for c in word) and (len(word) < 4 or word in _STOP):
            continue
        out.add(word[:STEM])
    return frozenset(out)


@dataclass(frozen=True)
class Hit:
    item: FeedItem
    score: float  # best weighted share of one query's words found in the item, in (0, 1]


@dataclass(frozen=True)
class Query:
    text: str
    language: str | None  # ISO 639-1; None matches items in any language


def _item_terms(item: FeedItem) -> frozenset[str]:
    # Some feeds put the whole article in the summary; the lead is enough to tell the topic,
    # and a full body would match almost any query on common words.
    return terms(f"{item.title} {item.summary[:SUMMARY_CHARS]}")


def relevance(
    item_terms: frozenset[str], queries: Iterable[frozenset[str]], weight: Mapping[str, float]
) -> float:
    """Best share of a query's word weight found in the item; 0 below MIN_SHARED words."""
    best = 0.0
    for query in queries:
        shared = query & item_terms
        if len(shared) >= MIN_SHARED:
            best = max(best, sum(weight[t] for t in shared) / sum(weight[t] for t in query))
    return best


def rank(items: Iterable[FeedItem], queries: Iterable[Query]) -> list[Hit]:
    """Items that match some query, best first (newer first on ties); one hit per URL.

    Words are weighted by rarity among the items read (inverse document frequency): "Italia" in
    an Italian agency's feed says little, "805" or "Garante" a lot.

    A query is compared only with items in its own language: across languages, shared stems are
    mostly false friends (Italian "fine" is "end"; Spanish "multa" and "garantías" are not about
    the Italian data-protection authority's fine).
    """
    by_language: dict[str | None, list[frozenset[str]]] = {}
    for query in queries:
        words = terms(query.text)
        if len(words) >= MIN_SHARED:
            by_language.setdefault(query.language, []).append(words)
    items = list(items)
    item_terms = [_item_terms(item) for item in items]
    frequency = Counter(t for words in item_terms for t in words)
    # A word no item uses weighs like the rarest: it still counts in the query's total.
    unseen = math.log(len(items) + 1) + 0.1
    weight: defaultdict[str, float] = defaultdict(lambda: unseen)
    for t, n in frequency.items():
        weight[t] = math.log((len(items) + 1) / (n + 1)) + 0.1
    hits: dict[str, Hit] = {}
    for item, words in zip(items, item_terms, strict=True):
        candidates = by_language.get(item.language, []) + by_language.get(None, [])
        if not candidates:
            continue
        score = relevance(words, candidates, weight)
        if score >= MIN_SHARE and (item.url not in hits or hits[item.url].score < score):
            hits[item.url] = Hit(item, score)
    return sorted(hits.values(), key=lambda h: (h.score, h.item.published_at or ""), reverse=True)
