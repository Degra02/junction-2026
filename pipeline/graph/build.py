"""Offline build of the source graph from stored analyses (plans/source-graph.md, phase 0).

    python -m pipeline.graph.build evals/results/fit.jsonl --labelled evals/labelled.jsonl

reads one analysis per line (bare, or wrapped as the eval runner writes them:
`{"item_id", "analysis"}`) and writes `evals/graph.json`.

Two outlets are tied by layers of evidence, each counted over distinct articles so one story
cannot make a strong tie:

- `analytics_id`: both carry the same Google Analytics or Tag Manager ID;
- `ad_account`: both carry the same AdSense publisher ID. Weak: such IDs also belong to ad
  resellers (in the eval records 2 of 10 shared ones matched a known common owner, against 12
  of 15 analytics IDs);
- `copy`: an article of one holds at least `COPY_CONTAINMENT` of the other's word 5-grams.
  Quoted passages, syndicated text (seen on a news agency or on `SYNDICATED_NEWSROOMS`
  newsrooms) and boilerplate are removed first; fact-checks, established newsrooms and official
  sites never copy (the rule of `signals.coordinated`);
- `translation`: articles in different languages whose headline and lead embed at
  `TRANSLATION_SIMILARITY` or more, at most `WINDOW_DAYS` apart;
- `link`: the analysed document of one links to the other. Shown, never coordination.

Outlets of one operator are tied by `same_operator` as well (affiliation). IDs found on a
hosting platform, placeholder IDs and IDs on more than `MAX_CARRIERS` operators are ignored.

Per layer `evidence = 1 - exp(-count / tau)`; layers combine as a noisy-OR weighted by how far
each can be trusted: `strength = 1 - prod(1 - q * evidence)`. `coordination` is the same over the
coordination layers only. A cluster is a connected component over ties with
`coordination >= CLUSTER_STRENGTH` or the same operator. Published lists (`known_network`) are
an attribute of an outlet and never make a tie, so the clusters are found without them.

Output: `built_at`, `counts`, `outlets[]` (`domain`, `operator`, `outlet_type`, `country`,
`known_network`, `articles`, `analysed`, `cluster`), `edges[]` (`a`, `b`, `strength`,
`coordination`, `layers[]` with `kind`, `count`, `evidence[]`), `clusters[]` (`id`, `outlets`,
`listed`, `joined_by`) and, with labels, `evaluation`.
"""

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path

import numpy as np

from pipeline.common.contracts import (
    Analysis,
    GraphObservation,
    GraphPatch,
    GraphPatchArticle,
    GraphPatchOutlet,
    OutletType,
)
from pipeline.graph.corpus import Article, Corpus, collect, hosted, official, operator, social
from pipeline.signals.coordinated import (
    COPY_CONTAINMENT,
    MIN_SHARED_SHINGLES,
    NOT_COPIERS,
    SHINGLE,
    TRANSLATED_COPY_SIMILARITY,
)
from pipeline.signals.text import mask_quotations, normalize_domain, tokens
from pipeline.story.assign import story_text

TRANSLATION_SIMILARITY = TRANSLATED_COPY_SIMILARITY
WINDOW_DAYS = 7
SYNDICATED_NEWSROOMS = 3
BOILERPLATE_OPERATORS = 8
MAX_CARRIERS = 20
CLUSTER_STRENGTH = 0.5
MAX_EVIDENCE = 3

ANALYTICS_ID, AD_ACCOUNT, COPY, TRANSLATION, LINK, SAME_OPERATOR = (
    "analytics_id",
    "ad_account",
    "copy",
    "translation",
    "link",
    "same_operator",
)
# kind -> (tau: count at which the layer reaches 63% of its evidence, q: trust in the layer).
# `analytics_id` q = 0.75 (down from 0.9 after M2 found 5 of 18 single-ID edges were shared CMS
# or partner-syndication tags: 1 uncorroborated ID scores 0.474 < CLUSTER_STRENGTH, while 2 IDs
# or 1 ID + copied text still cross 0.5). `translation` q = 0.8 matches `copy` so 2 translated
# stories (0.506) reach CLUSTER_STRENGTH.
LAYERS: dict[str, tuple[float, float]] = {
    ANALYTICS_ID: (1.0, 0.75),
    AD_ACCOUNT: (1.0, 0.2),
    COPY: (2.0, 0.8),
    TRANSLATION: (2.0, 0.8),
    LINK: (3.0, 0.3),
}
COORDINATION = frozenset({ANALYTICS_ID, AD_ACCOUNT, COPY, TRANSLATION})
# Layers that rest on shared text, which agency copy and press releases share too.
TEXT = frozenset({COPY, TRANSLATION})
_NEWSROOMS = frozenset({OutletType.wire_service, OutletType.national, OutletType.local})
_ANALYTICS = re.compile(r"^(UA-\d+(-\d+)?|G-[A-Z0-9]+|GTM-[A-Z0-9]+)$")
_AD_ACCOUNT = re.compile(r"^(?:ca-)?pub-(\d+)$")
# Digits of the IDs left in page templates: `pub-1234567890123456`, `pub-0000000000000000`.
_COUNTING = "01234567890123456789"

type Embed = Callable[[list[str]], np.ndarray]
# Text -> ISO 639-1 code, or None when no language is detected.
type Detect = Callable[[str], str | None]
type Pair = tuple[str, str]


@dataclass
class Tie:
    """One layer of evidence between two outlets `(a, b)`, `a < b`."""

    # What was seen on each side: article URLs, the shared IDs, or the linking analyses.
    a: set[str] = field(default_factory=set)
    b: set[str] = field(default_factory=set)
    evidence: list[dict[str, object]] = field(default_factory=list)
    # Analyses behind the evidence.
    analyses: set[str] = field(default_factory=set)

    @property
    def count(self) -> int:
        return min(len(self.a), len(self.b))


type Edges = dict[Pair, dict[str, Tie]]


def id_kind(value: str) -> str | None:
    """The layer a tracking ID belongs to, or None for an ID that proves nothing."""
    if _ANALYTICS.match(value):
        return ANALYTICS_ID
    if m := _AD_ACCOUNT.match(value):
        digits = m.group(1)
        return None if digits in _COUNTING or len(set(digits)) == 1 else AD_ACCOUNT
    return None


def republishes(article: Article, corpus: Corpus) -> bool:
    """Whether shared text with this article is its trade, not a tie: a fact-check, an
    established newsroom running agency copy, an official statement."""
    return (
        article.fact_check
        or corpus.outlets[article.outlet].outlet_type in NOT_COPIERS
        or official(article.outlet)
    )


def _shingles(text: str) -> set[int]:
    words = tokens(mask_quotations(text))
    return {hash(tuple(words[i : i + SHINGLE])) for i in range(len(words) - SHINGLE + 1)}


def _tie(edges: Edges, kind: str, x: Article, y: Article, **detail: object) -> None:
    if y.outlet < x.outlet:
        x, y = y, x
    tie = edges[(x.outlet, y.outlet)].setdefault(kind, Tie())
    tie.a.add(x.url)
    tie.b.add(y.url)
    tie.evidence.append({"a": x.url, "b": y.url, **detail})
    tie.analyses |= x.analyses | y.analyses


def copy_ties(corpus: Corpus, edges: Edges) -> None:
    articles = corpus.articles
    operators = [operator(a.outlet) for a in articles]
    types = [corpus.outlets[a.outlet].outlet_type for a in articles]
    sets = [_shingles(a.text) for a in articles]
    holders: dict[int, list[int]] = defaultdict(list)
    for index, shingles in enumerate(sets):
        for shingle in shingles:
            holders[shingle].append(index)
    repeated = {s: indices for s, indices in holders.items() if len(indices) > 1}
    # Text that is everyone's: agency copy and the boilerplate of shared widgets.
    common = set()
    for shingle, indices in repeated.items():
        by_operator = {operators[i]: types[i] for i in indices}
        if (
            len(by_operator) >= BOILERPLATE_OPERATORS
            or OutletType.wire_service in by_operator.values()
            or sum(t in _NEWSROOMS for t in by_operator.values()) >= SYNDICATED_NEWSROOMS
        ):
            common.add(shingle)
    own = [len(shingles - common) for shingles in sets]
    copiers = {i for i, a in enumerate(articles) if not republishes(a, corpus)}
    shared: dict[tuple[int, int], int] = defaultdict(int)
    for shingle, indices in repeated.items():
        if shingle in common:
            continue
        for i, j in combinations([i for i in indices if i in copiers], 2):
            if articles[i].outlet != articles[j].outlet:
                shared[(i, j)] += 1
    for (i, j), count in shared.items():
        share = count / min(own[i], own[j])
        if count >= MIN_SHARED_SHINGLES and share >= COPY_CONTAINMENT:
            _tie(edges, COPY, articles[i], articles[j], share=round(share, 2))


def translation_ties(corpus: Corpus, edges: Edges, embed: Embed, detect: Detect) -> None:
    articles = corpus.articles
    if not articles:
        return
    texts = [story_text(a.title, a.text) for a in articles]
    vectors = embed(texts)
    similarity = vectors @ vectors.T
    languages: dict[int, str | None] = {}

    def language(index: int) -> str | None:
        if index not in languages:
            languages[index] = detect(texts[index])
        return languages[index]

    close = np.nonzero(np.triu(similarity, 1) >= TRANSLATION_SIMILARITY)
    for i, j in zip(*(axis.tolist() for axis in close), strict=True):
        x, y = articles[i], articles[j]
        dated = x.published_at is not None and y.published_at is not None
        if (
            x.outlet == y.outlet
            or (dated and abs((x.published_at - y.published_at).days) > WINDOW_DAYS)
            or republishes(x, corpus)
            or republishes(y, corpus)
        ):
            continue
        ours, theirs = language(i), language(j)
        if ours and theirs and ours != theirs:
            _tie(edges, TRANSLATION, x, y, similarity=round(float(similarity[i, j]), 3))


def id_ties(corpus: Corpus, edges: Edges) -> None:
    platform_ids = {t for a in corpus.articles if hosted(a.outlet) for t in a.tracking_ids}
    carriers: dict[str, dict[str, Article]] = defaultdict(dict)
    for article in corpus.articles:
        for tracking_id in article.tracking_ids - platform_ids:
            carriers[tracking_id].setdefault(article.outlet, article)
    for tracking_id, sites in carriers.items():
        kind = id_kind(tracking_id)
        if kind is None or len({operator(d) for d in sites}) > MAX_CARRIERS:
            continue
        for x, y in combinations(sites.values(), 2):
            tie = edges[tuple(sorted((x.outlet, y.outlet)))].setdefault(kind, Tie())
            tie.a.add(tracking_id)
            tie.b.add(tracking_id)
            tie.evidence.append({"id": tracking_id})
            tie.analyses |= x.analyses | y.analyses


def link_ties(corpus: Corpus, edges: Edges) -> None:
    for (source, target), analyses in corpus.links.items():
        tie = edges[tuple(sorted((source, target)))].setdefault(LINK, Tie())
        # One per analysed document, whichever way the link points.
        tie.a |= analyses
        tie.b |= analyses
        tie.evidence.append({"from": source, "to": target})
        tie.analyses |= analyses


def ties(corpus: Corpus, embed: Embed, detect: Detect) -> Edges:
    """Every tie between two outlets, except `same_operator`, which the names give."""
    edges: Edges = defaultdict(dict)
    id_ties(corpus, edges)
    copy_ties(corpus, edges)
    translation_ties(corpus, edges, embed, detect)
    link_ties(corpus, edges)
    return edges


def strength(layers: dict[str, Tie], kinds: Iterable[str] = LAYERS) -> float:
    """Noisy-OR of the layers in `kinds`."""
    miss = 1.0
    for kind in kinds:
        if kind in layers:
            tau, trust = LAYERS[kind]
            miss *= 1.0 - trust * (1.0 - math.exp(-layers[kind].count / tau))
    return 1.0 - miss


def clusters(corpus: Corpus, edges: Edges, *, same_operator: bool = True) -> list[list[str]]:
    """Groups of two or more outlets joined by coordination-grade ties, largest first."""
    parent = {domain: domain for domain in corpus.outlets}

    def root(domain: str) -> str:
        while parent[domain] != domain:
            parent[domain] = parent[parent[domain]]
            domain = parent[domain]
        return domain

    for (a, b), layers in edges.items():
        if strength(layers, COORDINATION) >= CLUSTER_STRENGTH:
            parent[root(a)] = root(b)
    if same_operator:
        first: dict[str, str] = {}
        for domain in corpus.outlets:
            parent[root(domain)] = root(first.setdefault(operator(domain), domain))
    groups: dict[str, list[str]] = defaultdict(list)
    for domain in corpus.outlets:
        groups[root(domain)].append(domain)
    found = [sorted(group) for group in groups.values() if len(group) > 1]
    return sorted(found, key=lambda group: (-len(group), group))


def evaluation(corpus: Corpus, edges: Edges, sets: dict[str, str]) -> dict[str, object]:
    """How the clusters compare with the published lists, which never make a tie, and the
    text ties that rest only on analyses of hard negatives (agency copy, press releases...),
    where shared text is not coordination. `sets` maps an analysis ID to the labelled set of
    its item."""
    listed = {d for d, outlet in corpus.outlets.items() if outlet.known_network}

    def together(groups: list[list[str]]) -> tuple[int, list[str]]:
        mixed = [g for g in groups if len(listed.intersection(g)) > 1]
        return (
            sum(len(listed.intersection(g)) for g in mixed),
            sorted(d for g in mixed for d in g if d not in listed),
        )

    with_operator, unlisted = together(clusters(corpus, edges))
    without_operator, _ = together(clusters(corpus, edges, same_operator=False))
    tied = {
        d
        for pair, layers in edges.items()
        if listed.issuperset(pair) and strength(layers, COORDINATION) > 0
        for d in pair
    }
    neighbours = {
        d
        for pair, layers in edges.items()
        if strength(layers, COORDINATION) >= CLUSTER_STRENGTH
        and len(listed.intersection(pair)) == 1
        for d in pair
        if d not in listed
    }
    weak, strong = 0, []
    for (a, b), layers in sorted(edges.items()):
        text = TEXT.intersection(layers)
        behind = {sets.get(i, "unlabelled") for kind in text for i in layers[kind].analyses}
        if (
            not text
            or operator(a) == operator(b)
            or not all(name.startswith("hard_") or name == "mainstream" for name in behind)
        ):
            continue
        if strength(layers, TEXT) >= CLUSTER_STRENGTH:
            strong.append({"a": a, "b": b, "layers": sorted(text), "sets": sorted(behind)})
        else:
            weak += 1
    return {
        "listed_outlets": len(listed),
        "listed_clustered_together": with_operator,
        "listed_clustered_together_without_same_operator": without_operator,
        "listed_tied_to_another_listed_without_same_operator": len(tied),
        "unlisted_in_their_clusters": unlisted,
        "unlisted_strongly_tied_to_a_listed_outlet": sorted(neighbours),
        "text_ties_from_hard_negatives_only": {"weak": weak, "strong": strong},
    }


def _strongest(evidence: list[dict[str, object]]) -> list[dict[str, object]]:
    """The first `MAX_EVIDENCE` items, the closest matches first, in a stable order."""

    def key(item: dict[str, object]) -> tuple[float, str]:
        score = item.get("share", item.get("similarity", 0.0))
        return (-float(score), json.dumps(item, sort_keys=True))

    return sorted(evidence, key=key)[:MAX_EVIDENCE]


def graph(corpus: Corpus, edges: Edges) -> dict[str, object]:
    groups = clusters(corpus, edges)
    cluster_of = {domain: n for n, group in enumerate(groups, 1) for domain in group}
    articles: dict[str, list[Article]] = defaultdict(list)
    for article in corpus.articles:
        articles[article.outlet].append(article)
    by_operator: dict[str, list[str]] = defaultdict(list)
    for domain in sorted(corpus.outlets):
        by_operator[operator(domain)].append(domain)
    pairs = set(edges).union(*(combinations(group, 2) for group in by_operator.values()))
    out = []
    for a, b in pairs:
        layers = edges.get((a, b), {})
        same = operator(a) == operator(b)
        out.append(
            {
                "a": a,
                "b": b,
                "strength": 1.0 if same else round(strength(layers), 3),
                "coordination": round(strength(layers, COORDINATION), 3),
                "layers": ([{"kind": SAME_OPERATOR}] if same else [])
                + [
                    {"kind": kind, "count": tie.count, "evidence": _strongest(tie.evidence)}
                    for kind, tie in sorted(layers.items())
                ],
            }
        )
    out.sort(key=lambda e: (-e["coordination"], -e["strength"], e["a"], e["b"]))

    def joined_by(group: list[str]) -> list[str]:
        kinds: set[str] = set()
        for a, b in combinations(group, 2):
            layers = edges.get((a, b), {})
            if operator(a) == operator(b):
                kinds.add(SAME_OPERATOR)
            if strength(layers, COORDINATION) >= CLUSTER_STRENGTH:
                kinds |= COORDINATION.intersection(layers)
        return sorted(kinds)

    return {
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "counts": {
            "analyses": corpus.analyses,
            "articles": len(corpus.articles),
            "outlets": len(corpus.outlets),
            "edges": len(out),
            "clusters": len(groups),
        },
        "outlets": [
            {
                "domain": domain,
                "operator": operator(domain),
                "outlet_type": outlet.outlet_type.value if outlet.outlet_type else None,
                "country": outlet.country,
                "known_network": outlet.known_network,
                "articles": len(articles[domain]),
                "analysed": sum(a.analysed for a in articles[domain]),
                "cluster": cluster_of.get(domain),
            }
            for domain, outlet in sorted(corpus.outlets.items())
        ],
        "edges": out,
        "clusters": [
            {
                "id": n,
                "outlets": group,
                "listed": sum(bool(corpus.outlets[d].known_network) for d in group),
                "joined_by": joined_by(group),
            }
            for n, group in enumerate(groups, 1)
        ],
    }


def patch_for_analysis(analysis: Analysis, embed: Embed, detect: Detect) -> GraphPatch:
    """Observations of a single `Analysis` for live SQLite ingestion (`POST /stages/graph`, `L2`).

    Reuses `collect` and `ties` directly so live ingestion obeys the exact same rules as the
    offline build.
    """
    corpus = collect([analysis])
    if not corpus.articles:
        return GraphPatch(outlets=[], articles=[], ties=[])

    texts = [story_text(a.title, a.text) for a in corpus.articles]
    vectors = embed(texts)
    languages = [detect(t) for t in texts]
    lang_by_text = dict(zip(texts, languages, strict=True))

    edges = ties(corpus, lambda _ts: vectors, lambda t: lang_by_text.get(t))

    doc_outbound: list[str] = []
    if analysis.document and analysis.document.outbound_links:
        own_op = operator(normalize_domain(analysis.document.outlet) or "")
        seen_links: set[str] = set()
        for raw_link in analysis.document.outbound_links:
            target = normalize_domain(raw_link)
            if (
                target
                and not social(target)
                and operator(target) != own_op
                and target not in seen_links
            ):
                seen_links.add(target)
                doc_outbound.append(target)

    outlets = [
        GraphPatchOutlet(
            domain=domain,
            operator=operator(domain),
            outlet_type=outlet.outlet_type,
            country=outlet.country,
            known_network=outlet.known_network,
        )
        for domain, outlet in sorted(corpus.outlets.items())
    ]
    articles = [
        GraphPatchArticle(
            url=article.url,
            outlet=article.outlet,
            title=article.title,
            published_at=article.published_at,
            language=lang,
            analysed=article.analysed,
            fact_check=article.fact_check,
            tracking_ids=sorted(article.tracking_ids),
            outbound_domains=doc_outbound if article.analysed else [],
            embedding=[round(float(v), 6) for v in vec.tolist()],
        )
        for article, vec, lang in zip(corpus.articles, vectors, languages, strict=True)
    ]
    observations = [
        GraphObservation(
            a=a,
            b=b,
            kind=kind,
            keys_a=sorted(tie.a),
            keys_b=sorted(tie.b),
            evidence=_strongest(tie.evidence),
        )
        for (a, b), layers in sorted(edges.items())
        for kind, tie in sorted(layers.items())
    ]
    return GraphPatch(outlets=outlets, articles=articles, ties=observations)


def _records(path: Path) -> Iterator[tuple[Analysis, str | None]]:
    with path.open(encoding="utf-8") as lines:
        for line in lines:
            if line.strip():
                record = json.loads(line)
                wrapped = "analysis" in record
                yield (
                    Analysis.model_validate(record["analysis"] if wrapped else record),
                    record.get("item_id") if wrapped else None,
                )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("analyses", type=Path, help="JSON lines: analyses, or eval fit records")
    parser.add_argument("--out", type=Path, default=Path("evals/graph.json"))
    parser.add_argument(
        "--labelled",
        type=Path,
        help="the labelled set (evals/labelled.jsonl): adds `evaluation` for eval fit records",
    )
    args = parser.parse_args(argv)

    # Both load a model: not at import, so the tests and `--help` stay light.
    from pipeline.extract.language import detect_language
    from pipeline.story.model import embed

    def detect(text: str) -> str | None:
        language = detect_language([text])
        return language.code if language else None

    records = list(_records(args.analyses))
    corpus = collect(analysis for analysis, _ in records)
    edges = ties(corpus, embed, detect)
    result = graph(corpus, edges)
    if args.labelled:
        with args.labelled.open(encoding="utf-8") as lines:
            set_of_item = {(item := json.loads(line))["id"]: item["set"] for line in lines}
        sets = {str(a.id): set_of_item[item] for a, item in records if item in set_of_item}
        result["evaluation"] = evaluation(corpus, edges, sets)
    args.out.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{args.out}: {json.dumps(result['counts'])}")
    if args.labelled:
        print(json.dumps(result["evaluation"], indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
