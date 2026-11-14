"""Families `claim_support` and `fact_checks`: the key claims against the retrieved context.

- `claim_support` / `contradicted`: value = (contradicting sources + 1) / (sources that address
  the claim + 2), in `(0, 1)`: the contradicting share, pulled toward 0.5 by one imaginary source
  each way so that a single source moves it little (1 of 1 → 0.67, 8 of 8 → 0.9, 0 of 4 → 0.17).
  One item per claim that at least one source addresses. Peers come from `story_peers` (copies
  of the document excluded); a peer that repeats the claim word for word is a quote, not
  confirmation, and is skipped for that claim.
- `claim_support` / `unaddressed`: value 1.0 when none of at least MIN_PEERS sources
  addresses the claim.
- `fact_checks` / `rated_false` (1.0), `rated_misleading` (0.6), `rated_true` (0.0): a
  published fact-check that matches a key claim (by entailment/overlap with the reviewed claim,
  or, for false/misleading ratings across languages or phrasings, when the fact-checker's own
  debunking verdict contradicts the claim in both directions). Ratings outside the vocabulary
  below are skipped rather than guessed.

NLI is cross-lingual: a claim in Italian is checked against English coverage and vice versa.

A source contradicts a claim only when passage and claim contradict each other in both
directions with probability >= CONTRADICTION. The NLI model assumes its two texts describe the
same situation, so two reports of different moments of one story ("the envoys travelled to
Dublin on Thursday" / "the envoys arrived in Moscow on Thursday") look contradictory to it.
Measured on Sat 14.11 on 50 claim-source pairs from BBC, tagesschau and RTÉ reports and their
story peers, where a contradiction is almost surely false: the one-direction rule at 0.6
flagged 21, both directions at 0.9 flag 7, while the real contradictions among the controls
(a denial of the claim, in the same or another language) score 0.96 or more both ways. The
remaining false contradictions are why the combiner's weight for this family must come from
labelled data.
"""

import re
from collections.abc import Callable, Sequence

import numpy as np

from pipeline.common.contracts import Claim, ContextItem, DocumentRef, Evidence, Family
from pipeline.signals.text import contains, context_ref, overlap, sentence_windows

type Nli = Callable[[list[tuple[str, str]]], np.ndarray]

ENTAIL, CONTRADICT = 0, 2
# A source supports a claim when one of its passages entails it this strongly.
DECISIVE = 0.6
# A source contradicts a claim when a passage and the claim contradict each other this strongly
# in both directions (see the module docstring).
CONTRADICTION = 0.9
# Two-sentence windows per (claim, peer) sent to NLI: the ones sharing most words with the claim.
PASSAGES_PER_PEER = 4
MIN_PEERS = 3
# A fact-check matches a claim when either entails the other this strongly, or on word overlap.
FACT_CHECK_ENTAIL = 0.5
FACT_CHECK_OVERLAP = 0.6
VERDICT_PASSAGES = 6
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
    forward = nli([(passage, claims[ci].text) for ci, _, passage in jobs])
    # The reverse direction only where it can matter: it doubles the cost of a pair.
    suspects = [k for k, probs in enumerate(forward) if probs[CONTRADICT] >= CONTRADICTION]
    backward = nli([(claims[jobs[k][0]].text, jobs[k][2]) for k in suspects])
    contradiction = np.zeros(len(jobs))
    for k, probs in zip(suspects, backward, strict=True):
        contradiction[k] = min(float(forward[k][CONTRADICT]), float(probs[CONTRADICT]))

    # Best entailment and contradiction per (claim, peer), with the passage behind each.
    best: dict[tuple[int, int], dict[int, tuple[float, str]]] = {}
    for k, (ci, pi, passage) in enumerate(jobs):
        slot = best.setdefault((ci, pi), {ENTAIL: (0.0, ""), CONTRADICT: (0.0, "")})
        for label, p in ((ENTAIL, float(forward[k][ENTAIL])), (CONTRADICT, contradiction[k])):
            if p > slot[label][0]:
                slot[label] = (p, passage)

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
            if contra >= CONTRADICTION and contra > entail:
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
                    value=round((len(contradicting) + 1) / (addressing + 2), 3),
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
        verdict_quote: str | None = None
        if (
            probabilities[k, j] < FACT_CHECK_ENTAIL
            and _overlap_score(check.fact_check.claim, claims[j].text) < FACT_CHECK_OVERLAP
        ):
            if signal[0] not in {"rated_false", "rated_misleading"}:
                continue
            matched = _verdict_match(check, claims, nli)
            if matched is None:
                continue
            j, verdict_quote = matched
        rating = check.fact_check.rating
        publisher = check.fact_check.publisher or check.outlet or "A fact-checker"
        quote = (
            verdict_quote
            if verdict_quote and verdict_quote in check.text
            else (rating if rating in check.text else None)
        )
        evidence.append(
            Evidence(
                id=next_id(),
                family=Family.fact_checks,
                signal=signal[0],
                value=signal[1],
                detail=f"{publisher} rated this claim “{rating}”.",
                source_refs=[
                    DocumentRef(kind="document", span=claims[j].span),
                    context_ref(check, quote),
                ],
            )
        )
    return evidence


def _verdict_match(check: ContextItem, claims: Sequence[Claim], nli: Nli) -> tuple[int, str] | None:
    """`(claim_index, verdict_passage)` when a passage of `check` debunks both the reviewed
    claim (`>= DECISIVE` two-way contradiction) and a document claim (`>= CONTRADICTION`
    two-way contradiction). Catches cross-lingual or differently scoped phrasings of the same
    hoax while rejecting the quoted hoax line itself and unrelated claims in roundup articles.
    """
    assert check.fact_check is not None
    candidates: list[str] = []
    if check.title and check.title.strip():
        candidates.append(check.title.strip())
    for window in sentence_windows(check.text):
        if window not in candidates:
            candidates.append(window)
        if len(candidates) >= VERDICT_PASSAGES:
            break
    if not candidates:
        return None
    reviewed = check.fact_check.claim
    vs_reviewed = nli([(p, reviewed) for p in candidates] + [(reviewed, p) for p in candidates])
    n_cand = len(candidates)
    verdicts = [
        candidates[i]
        for i in range(n_cand)
        if min(float(vs_reviewed[i, CONTRADICT]), float(vs_reviewed[n_cand + i, CONTRADICT]))
        >= DECISIVE
    ]
    if not verdicts:
        return None
    pairs = [(v, claim.text) for v in verdicts for claim in claims]
    forward = nli(pairs)
    suspects = [i for i, probs in enumerate(forward) if probs[CONTRADICT] >= CONTRADICTION]
    if not suspects:
        return None
    backward = nli([(pairs[i][1], pairs[i][0]) for i in suspects])
    best: tuple[float, int, str] | None = None
    for i, probs in zip(suspects, backward, strict=True):
        both = min(float(forward[i, CONTRADICT]), float(probs[CONTRADICT]))
        if both >= CONTRADICTION and (best is None or both > best[0]):
            best = (both, i % len(claims), pairs[i][0])
    return (best[1], best[2]) if best else None


def _overlap_score(a: str, b: str) -> float:
    return min(overlap(a, b), overlap(b, a))
