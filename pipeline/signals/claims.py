"""Families `claim_support` and `fact_checks`: the key claims against the retrieved context.

- `claim_support` / `contradicted`: value = contradicting sources / sources that address the
  claim (support or contradict it), in `[0, 1]`. One item per claim that at least one source
  addresses. Peers come from `story_peers` (copies of the document excluded); a peer that
  repeats the claim word for word is a quote, not confirmation, and is skipped for that claim.
- `claim_support` / `unaddressed`: value 1.0 when none of at least MIN_PEERS sources
  addresses the claim.
- `fact_checks` / `rated_false` (1.0), `rated_misleading` (0.6), `rated_true` (0.0): a
  published fact-check that matches a key claim. Ratings outside the vocabulary below are
  skipped rather than guessed.

NLI is cross-lingual: a claim in Italian is checked against English coverage and vice versa.
"""

import re
from collections.abc import Callable, Sequence

import numpy as np

from pipeline.common.contracts import Claim, ContextItem, DocumentRef, Evidence, Family
from pipeline.signals.text import contains, context_ref, overlap, sentence_windows

type Nli = Callable[[list[tuple[str, str]]], np.ndarray]

ENTAIL, CONTRADICT = 0, 2
# A source addresses a claim when one of its passages entails or contradicts it this strongly.
DECISIVE = 0.6
# Two-sentence windows per (claim, peer) sent to NLI: the ones sharing most words with the claim.
PASSAGES_PER_PEER = 4
MIN_PEERS = 3
# A fact-check matches a claim when either entails the other this strongly, or on word overlap.
FACT_CHECK_ENTAIL = 0.5
FACT_CHECK_OVERLAP = 0.6
_MAX_REFS = 4

# Checked in order; the first match wins. Lower-case substrings of the published rating.
RATINGS: list[tuple[str, float, tuple[str, ...]]] = [
    (
        "rated_misleading",
        0.6,
        (
            "mostly false",
            "half",
            "partly",
            "partially",
            "mixture",
            "mixed",
            "misleading",
            "missing context",
            "out of context",
            "exaggerat",
            "unproven",
            "unsupported",
            "fuorviante",
            "parzialmente",
            "c'eri quasi",
            "trompeur",
            "en partie",
            "irreführend",
            "teilweise",
            "engañoso",
            "parcialmente",
            "enganoso",
            "manipul",
            "częściowo",
            "вводит в заблуждение",
        ),
    ),
    (
        "rated_false",
        1.0,
        (
            "false",
            "fake",
            "not true",
            "untrue",
            "incorrect",
            "inaccurate",
            "wrong",
            "hoax",
            "fabricated",
            "pants on fire",
            "pinocchio",
            "baseless",
            "falso",
            "falsa",
            "bufala",
            "panzana",
            "faux",
            "fausse",
            "falsch",
            "fałsz",
            "nieprawda",
            "ложь",
            "фейк",
            "неправда",
            "onwaar",
        ),
    ),
    (
        "rated_true",
        0.0,
        (
            "true",
            "correct",
            "accurate",
            "vero",
            "vera",
            "vrai",
            "wahr",
            "richtig",
            "verdadero",
            "verdadeiro",
            "prawda",
            "правда",
            "waar",
        ),
    ),
]


def claim_support_evidence(
    claims: Sequence[Claim],
    peers: Sequence[ContextItem],
    nli: Nli,
    next_id: Callable[[], str],
) -> list[Evidence]:
    if not claims or not peers:
        return []
    # (claim index, peer index, passage) for the passages most likely to talk about the claim.
    jobs: list[tuple[int, int, str]] = []
    for ci, claim in enumerate(claims):
        for pi, peer in enumerate(peers):
            if contains(peer.text, claim.text):
                continue
            passages = sorted(sentence_windows(peer.text), key=lambda c: -overlap(claim.text, c))
            jobs += [(ci, pi, passage) for passage in passages[:PASSAGES_PER_PEER]]
    probabilities = nli([(passage, claims[ci].text) for ci, _, passage in jobs])

    # Best entailment and contradiction per (claim, peer), with the passage behind each.
    best: dict[tuple[int, int], dict[int, tuple[float, str]]] = {}
    for (ci, pi, passage), probs in zip(jobs, probabilities, strict=True):
        slot = best.setdefault((ci, pi), {})
        for label in (ENTAIL, CONTRADICT):
            if float(probs[label]) > slot.get(label, (0.0, ""))[0]:
                slot[label] = (float(probs[label]), passage)

    evidence = []
    for ci, claim in enumerate(claims):
        supporting: list[int] = []
        contradicting: list[tuple[int, str]] = []
        judged = 0
        for pi in range(len(peers)):
            slot = best.get((ci, pi))
            if slot is None:
                continue
            judged += 1
            entail, _ = slot[ENTAIL]
            contra, passage = slot[CONTRADICT]
            if contra >= DECISIVE and contra > entail:
                contradicting.append((pi, passage))
            elif entail >= DECISIVE:
                supporting.append(pi)
        addressing = len(supporting) + len(contradicting)
        claim_ref = DocumentRef(kind="document", span=claim.span)
        if addressing:
            evidence.append(
                Evidence(
                    id=next_id(),
                    family=Family.claim_support,
                    signal="contradicted",
                    value=round(len(contradicting) / addressing, 3),
                    detail=f"{len(contradicting)} of the {addressing} sources that address the "
                    f"claim contradict it, {len(supporting)} support it.",
                    source_refs=[claim_ref]
                    + [context_ref(peers[pi], passage) for pi, passage in contradicting[:_MAX_REFS]]
                    + [context_ref(peers[pi]) for pi in supporting[: _MAX_REFS - 1]],
                )
            )
        elif judged >= MIN_PEERS:
            evidence.append(
                Evidence(
                    id=next_id(),
                    family=Family.claim_support,
                    signal="unaddressed",
                    value=1.0,
                    detail=f"None of the {judged} other reports on the event confirms or "
                    "contradicts the claim.",
                    source_refs=[claim_ref],
                )
            )
    return evidence


def rating_signal(rating: str) -> tuple[str, float] | None:
    """`(signal, value)` for a published rating, or None when the rating is not recognised."""
    text = rating.casefold()
    for signal, value, needles in RATINGS:
        for needle in needles:
            # Whole-word match for short Latin needles ("vero" must not match "severo").
            pattern = rf"(?<!\w){re.escape(needle)}" if needle.isascii() else re.escape(needle)
            if re.search(pattern, text):
                return signal, value
    return None


def fact_check_evidence(
    claims: Sequence[Claim],
    context: Sequence[ContextItem],
    nli: Nli,
    next_id: Callable[[], str],
    own_outlet: str | None = None,
) -> list[Evidence]:
    """Fact-checks from the document's own outlet are skipped: when the document is a
    fact-check, its own review of the claim it debunks is not evidence against it."""
    checks = [
        c
        for c in context
        if c.fact_check is not None and (own_outlet is None or c.outlet != own_outlet)
    ]
    if not claims or not checks:
        return []
    pairs = []
    for check in checks:
        assert check.fact_check is not None
        for claim in claims:
            pairs += [(check.fact_check.claim, claim.text), (claim.text, check.fact_check.claim)]
    probabilities = nli(pairs)[:, ENTAIL].reshape(len(checks), len(claims), 2).max(axis=2)

    evidence = []
    for k, check in enumerate(checks):
        assert check.fact_check is not None
        signal = rating_signal(check.fact_check.rating)
        if signal is None:
            continue
        scores = [
            max(float(probabilities[k, j]), _overlap_score(check.fact_check.claim, claim.text))
            for j, claim in enumerate(claims)
        ]
        j = int(np.argmax(scores))
        if (
            probabilities[k, j] < FACT_CHECK_ENTAIL
            and _overlap_score(check.fact_check.claim, claims[j].text) < FACT_CHECK_OVERLAP
        ):
            continue
        rating = check.fact_check.rating
        publisher = check.fact_check.publisher or check.outlet or "A fact-checker"
        evidence.append(
            Evidence(
                id=next_id(),
                family=Family.fact_checks,
                signal=signal[0],
                value=signal[1],
                detail=f"{publisher} rated this claim “{rating}”.",
                source_refs=[
                    DocumentRef(kind="document", span=claims[j].span),
                    context_ref(check, rating if rating in check.text else None),
                ],
            )
        )
    return evidence


def _overlap_score(a: str, b: str) -> float:
    return min(overlap(a, b), overlap(b, a))
