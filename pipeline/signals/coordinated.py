"""`run_coordinated`: evidence that the content is pushed by several sites together (plan §4 5b).

Works from the record only: no models, no network I/O. Families and values:

- `text_reuse` / `copied_passages`: number of distinct other outlets whose text contains a
  large share of the document's word 5-grams. Syndication is the main false positive (plan
  §12): passages that also appear in wire copy are removed first, and outlets typed as news
  agencies, fact-checkers, satire sites, national or local newsrooms never count as copiers
  (established newsrooms republishing the same text within minutes is agency copy even when the
  agency's
  own item was not retrieved). Passages the document quotes are not its own text and are
  removed too: a fact-check quoting a hoax is not a copy of it.
- `timing` / `copies_within_window`: number of those copies published within WINDOW of the
  document (or of the earliest copy when the document has no date).
- `infrastructure` / `shared_tracking_id`: largest number of other domains carrying one of the
  analytics or ad IDs of the document (or, without document IDs, of another copying site).
- `infrastructure` / `young_copying_domains`: copying domains registered less than
  YOUNG_DAYS before the document.
- `known_networks` / `listed_domain`: the document's outlet or a copying outlet is on a
  documented list (`sources[].known_network`, e.g. VIGINUM Portal Kombat); also includes
  same-story sister sites of the document's own network (or near-duplicate `>= 0.93` matches
  for pasted text). Value = listed domains.
"""

from collections import defaultdict
from collections.abc import Callable
from datetime import timedelta
from itertools import count

from pipeline.common.contracts import (
    Analysis,
    ContextItem,
    DocumentRef,
    Evidence,
    Family,
    OutletType,
    SignalsPatch,
    SourceProfile,
    Span,
    UrlRef,
)
from pipeline.signals.text import context_ref, own_words, sentence_spans, tokens

SHINGLE = 5
# Share of the document's (non-wire) 5-grams a context item must contain to count as a copy.
COPY_CONTAINMENT = 0.2
MIN_SHARED_SHINGLES = 8
WINDOW = timedelta(hours=6)
YOUNG_DAYS = 180
TRANSLATED_COPY_SIMILARITY = 0.93
_NOT_COPIERS = {
    OutletType.wire_service,
    OutletType.fact_checker,
    OutletType.satire,
    OutletType.national,
    OutletType.local,
}
_MAX_REFS = 4


def run_coordinated(analysis: Analysis) -> SignalsPatch:
    next_id = (f"c{n}" for n in count(1)).__next__
    copies = find_copies(analysis)
    evidence = text_reuse_evidence(analysis, copies, next_id)
    evidence += timing_evidence(analysis, copies, next_id)
    evidence += infrastructure_evidence(analysis, copies, next_id)
    evidence += known_network_evidence(analysis, copies, next_id)
    return SignalsPatch(evidence=evidence)


def find_copies(analysis: Analysis) -> list[ContextItem]:
    """One context item per other outlet that copies the document, most copied first."""
    document = analysis.document
    if document is None:
        return []
    profiles = _profiles(analysis)
    own = _domain(document.outlet)
    wire = set().union(
        *(
            _shingles(c.text)
            for c in analysis.context
            if _type(profiles, c.outlet) == OutletType.wire_service
        )
    )
    mine = _shingles("\n".join(own_words(document.paragraphs))) - wire
    if len(mine) < MIN_SHARED_SHINGLES:
        return []
    best: dict[str, tuple[float, ContextItem]] = {}
    for item in analysis.context:
        domain = _domain(item.outlet) or _domain(item.url)
        if (
            item.fact_check is not None
            or not domain
            or domain == own
            or _type(profiles, item.outlet) in _NOT_COPIERS
        ):
            continue
        shared = len(mine & _shingles(item.text))
        containment = shared / len(mine)
        if (
            shared >= MIN_SHARED_SHINGLES
            and containment >= COPY_CONTAINMENT
            and (domain not in best or containment > best[domain][0])
        ):
            best[domain] = (containment, item)
    return [item for _, item in sorted(best.values(), key=lambda x: -x[0])]


def text_reuse_evidence(
    analysis: Analysis, copies: list[ContextItem], next_id: Callable[[], str]
) -> list[Evidence]:
    if not copies or analysis.document is None:
        return []
    refs: list = []
    copied = _copied_sentence(analysis, copies)
    if copied is not None:
        refs.append(DocumentRef(kind="document", span=copied[0]))
    for item in copies[:_MAX_REFS]:
        quote = copied[1] if copied is not None and copied[1] in item.text else None
        refs.append(context_ref(item, quote))
    n = len(copies)
    sites = ", ".join(_domain(c.outlet) or c.url for c in copies[:3])
    return [
        Evidence(
            id=next_id(),
            family=Family.text_reuse,
            signal="copied_passages",
            value=float(n),
            detail=f"The same text appears on {n} other site{'s' if n > 1 else ''} that are "
            f"not news agencies ({sites}{', …' if n > 3 else ''}).",
            source_refs=refs,
        )
    ]


def timing_evidence(
    analysis: Analysis, copies: list[ContextItem], next_id: Callable[[], str]
) -> list[Evidence]:
    dated = [c for c in copies if c.published_at is not None]
    published = analysis.document.published_at if analysis.document else None
    anchor = published or min((c.published_at for c in dated if c.published_at), default=None)
    if anchor is None:
        return []
    close = [c for c in dated if c.published_at and abs(c.published_at - anchor) <= WINDOW]
    # Without the document's date, the earliest copy is the anchor and counts itself.
    if len(close) < (1 if published else 2):
        return []
    spread = max(abs(c.published_at - anchor) for c in close if c.published_at)
    what = "the article" if published else "each other"
    n = len(close)
    return [
        Evidence(
            id=next_id(),
            family=Family.timing,
            signal="copies_within_window",
            value=float(n),
            detail=f"{n} cop{'ies' if n > 1 else 'y'} appeared within {_duration(spread)} of "
            f"{what}.",
            source_refs=[context_ref(c) for c in close[:_MAX_REFS]],
        )
    ]


def infrastructure_evidence(
    analysis: Analysis, copies: list[ContextItem], next_id: Callable[[], str]
) -> list[Evidence]:
    document = analysis.document
    own = _domain(document.outlet) if document else None
    evidence = []

    # Tracking ID -> context items of other domains carrying it.
    carriers: dict[str, dict[str, ContextItem]] = defaultdict(dict)
    for item in analysis.context:
        domain = _domain(item.outlet) or _domain(item.url)
        if domain and domain != own:
            for tracking_id in item.tracking_ids:
                carriers[tracking_id].setdefault(domain, item)
    wanted = set(document.tracking_ids) if document and document.tracking_ids else set()
    if wanted:
        candidates = {t: carriers[t] for t in wanted if carriers.get(t)}
        needed = 1
    else:
        # No IDs on the document (pasted text): IDs shared by two or more copying sites.
        copying = {_domain(c.outlet) or _domain(c.url) for c in copies}
        candidates = {
            t: {d: i for d, i in sites.items() if d in copying} for t, sites in carriers.items()
        }
        needed = 2
    candidates = {t: sites for t, sites in candidates.items() if len(sites) >= needed}
    if candidates:
        tracking_id, sites = max(candidates.items(), key=lambda kv: (len(kv[1]), kv[0]))
        n = len(sites)
        whose = "the article's" if wanted else "the same"
        evidence.append(
            Evidence(
                id=next_id(),
                family=Family.infrastructure,
                signal="shared_tracking_id",
                value=float(n),
                detail=f"{n} other site{'s' if n > 1 else ''} carr{'y' if n > 1 else 'ies'} "
                f"{whose} analytics ID ({tracking_id}).",
                source_refs=[context_ref(i) for i in list(sites.values())[:_MAX_REFS]],
            )
        )

    profiles = _profiles(analysis)
    published = (document.published_at if document else None) or analysis.created_at
    young = [
        (c, profile)
        for c in copies
        if (profile := profiles.get(_domain(c.outlet) or ""))
        and profile.registered_at is not None
        and (published - profile.registered_at).days < YOUNG_DAYS
    ]
    if young:
        n = len(young)
        evidence.append(
            Evidence(
                id=next_id(),
                family=Family.infrastructure,
                signal="young_copying_domains",
                value=float(n),
                detail=f"{n} of the copying sites registered their domain less than "
                f"{YOUNG_DAYS} days before the article.",
                source_refs=[
                    UrlRef(kind="url", url=f"https://rdap.org/domain/{p.domain}")
                    for _, p in young[:_MAX_REFS]
                ],
            )
        )
    return evidence


def known_network_evidence(
    analysis: Analysis, copies: list[ContextItem], next_id: Callable[[], str]
) -> list[Evidence]:
    profiles = _profiles(analysis)
    own = _domain(analysis.document.outlet) if analysis.document else None
    own_network = profiles[own].known_network if own and own in profiles else None
    copy_domains = {_domain(c.outlet) or "" for c in copies}
    # `in_story` means same event, not same text: a mainstream report on an event a listed
    # network also covers must never inherit the network's listing. Count non-copy in-story
    # items only as sister editions of the document's own listed network, or at near-duplicate
    # similarity when the input was pasted text (no document outlet).
    story_domains = [
        d
        for c in analysis.context
        if c.in_story is True
        and c.fact_check is None
        and (d := _domain(c.outlet) or "") in profiles
        and (
            (own_network is not None and profiles[d].known_network == own_network)
            or (own is None and (c.similarity or 0.0) >= TRANSLATED_COPY_SIMILARITY)
        )
    ]
    candidates = ([own] if own else []) + [_domain(c.outlet) or "" for c in copies] + story_domains
    domains = list(dict.fromkeys(d for d in candidates if d))
    listed = [(d, profiles[d].known_network) for d in domains if d in profiles]
    listed = [(d, network) for d, network in listed if network]
    if not listed:
        return []
    networks = ", ".join(sorted({str(n).replace("_", " ") for _, n in listed}))
    if len(listed) > 1:
        who = f"{len(listed)} sites involved"
    elif listed[0][0] == own:
        who = "The site itself"
    elif listed[0][0] in copy_domains:
        who = "A site copying it"
    else:
        who = "Another site covering the story"
    return [
        Evidence(
            id=next_id(),
            family=Family.known_networks,
            signal="listed_domain",
            value=float(len(listed)),
            detail=f"{who} {'is' if len(listed) == 1 else 'are'} on a published list of a "
            f"documented network ({networks}).",
            source_refs=[UrlRef(kind="url", url=f"https://{d}") for d, _ in listed[:_MAX_REFS]],
        )
    ]


def _copied_sentence(analysis: Analysis, copies: list[ContextItem]) -> tuple[Span, str] | None:
    """The longest document sentence found word for word in the most copies."""
    assert analysis.document is not None
    best: tuple[int, int, Span, str] | None = None
    for index, paragraph in enumerate(analysis.document.paragraphs):
        for start, end in sentence_spans(paragraph):
            sentence = paragraph[start:end]
            hits = sum(sentence in c.text for c in copies)
            if hits and (best is None or (hits, len(sentence)) > (best[0], best[1])):
                best = (hits, len(sentence), Span(paragraph=index, start=start, end=end), sentence)
    return (best[2], best[3]) if best else None


def _shingles(text: str) -> set[tuple[str, ...]]:
    words = tokens(text)
    return {tuple(words[i : i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)}


def _profiles(analysis: Analysis) -> dict[str, SourceProfile]:
    return {_domain(s.domain) or s.domain: s for s in analysis.sources}


def _type(profiles: dict[str, SourceProfile], outlet: str | None) -> OutletType | None:
    profile = profiles.get(_domain(outlet) or "")
    return profile.outlet_type if profile else None


def _domain(value: str | None) -> str | None:
    """`https://www.Example.com/x` and `www.example.com` both become `example.com`."""
    if not value:
        return None
    host = value.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
    return host.removeprefix("www.") or None


def _duration(delta: timedelta) -> str:
    minutes = max(int(delta.total_seconds() // 60), 1)
    if minutes < 120:
        return f"{minutes} minute{'s' if minutes > 1 else ''}"
    return f"{minutes // 60} hours"
