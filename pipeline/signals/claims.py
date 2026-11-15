"""Families `claim_support` and `fact_checks`: the key claims against the retrieved context.

- `claim_support` / `contradicted`: value = (contradicting sources + 1) / (sources that address
  the claim + 2), in `(0, 1)`: the contradicting share, pulled toward 0.5 by one imaginary source
  each way so that a single source moves it little (1 of 1 → 0.67, 8 of 8 → 0.9, 0 of 4 → 0.17).
  One item per claim that at least one source addresses. Peers come from `story_peers` (copies
  and duplicate outlet domains excluded); a peer that repeats the claim word for word is a
  quote, not confirmation, and is skipped for that claim.
- `claim_support` / `unaddressed`: value 1.0 when none of at least MIN_PEERS sources
  addresses the claim.
- `fact_checks` / `rated_false` (1.0), `rated_misleading` (0.6), `rated_true` (0.0): a
  published fact-check that matches a key claim or `topic.implied_claims` (by entailment/overlap
  with the reviewed claim, or, for false/misleading ratings across languages or phrasings, when
  the fact-checker's own debunking verdict contradicts the claim in both directions). Implied
  claims have no document span, so their evidence cites the fact-check context item only. Ratings
  outside the vocabulary below are skipped rather than guessed.

System-One + selective cascade (`systemone`, `judge.verify_pairs`):
- Cross-lingual NLI (`mDeBERTa-v3-base-xnli`) runs locally on unquoted peer windows first,
  producing calibrated `[supports, contradicts, not_addressed]` probabilities in milliseconds.
- Confident `supports` (`>= DECISIVE`) and `not_addressed` pairs resolve locally in System 1
  with zero network calls.
- Candidate two-way contradictions (`>= S1_SUSPECT_CONTRA`) are the exact region where NLI
  confuses two moments of one story ("travelled to Dublin" vs "arrived in Moscow", or "had not
  been confirmed until now"): those pairs escalate in one batched typed call to `cascade`. When
  `cascade` is `None` or offline, strict two-way NLI (`>= CONTRADICTION`) decides locally.
"""

import re
from collections.abc import Callable, Sequence

import numpy as np

from pipeline.common.contracts import Claim, ContextItem, DocumentRef, Evidence, Family, Span
from pipeline.signals.systemone import calibrate_choice
from pipeline.signals.text import (
    contains,
    context_ref,
    mask_quotations,
    overlap,
    sentence_windows,
)

type Nli = Callable[[list[tuple[str, str]]], np.ndarray]
type Cascade = Callable[[Sequence[tuple[str, str]]], Sequence[str | None]]

ENTAIL, CONTRADICT = 0, 2
# System-1 thresholds on unquoted two-sentence windows (`mDeBERTa-v3-base-xnli`).
DECISIVE = 0.6
S1_SUSPECT_CONTRA = 0.75
CONTRADICTION = 0.9
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
    cascade: Cascade | None = None,
) -> list[Evidence]:
    if not claims or not peers:
        return []
    # (claim index, peer index, raw passage, unquoted passage) for windows sharing claim words.
    jobs: list[tuple[int, int, str, str]] = []
    for ci, claim in enumerate(claims):
        for pi, peer in enumerate(peers):
            if contains(peer.text, claim.text):
                continue
            passages = sorted(sentence_windows(peer.text), key=lambda c: -overlap(claim.text, c))
            for passage in passages[:PASSAGES_PER_PEER]:
                unquoted = mask_quotations(passage)
                jobs.append((ci, pi, passage, unquoted))
    if not jobs:
        return []

    forward = nli([(unquoted, claims[ci].text) for ci, _, _, unquoted in jobs])
    # Reverse NLI only where forward contradiction enters the System-1 suspect band.
    rev_indices = [k for k, probs in enumerate(forward) if probs[CONTRADICT] >= S1_SUSPECT_CONTRA]
    backward = (
        nli([(claims[jobs[k][0]].text, jobs[k][3]) for k in rev_indices])
        if rev_indices
        else np.zeros((0, 3))
    )
    contradiction = np.zeros(len(jobs))
    for k, probs in zip(rev_indices, backward, strict=True):
        contradiction[k] = min(float(forward[k][CONTRADICT]), float(probs[CONTRADICT]))

    # Best entailment and two-way contradiction per (claim, peer), with the raw passage.
    best: dict[tuple[int, int], dict[int, tuple[float, str]]] = {}
    for k, (ci, pi, passage, _) in enumerate(jobs):
        slot = best.setdefault((ci, pi), {ENTAIL: (0.0, ""), CONTRADICT: (0.0, "")})
        for label, p in (
            (ENTAIL, float(forward[k][ENTAIL])),
            (CONTRADICT, float(contradiction[k])),
        ):
            if p > slot[label][0]:
                slot[label] = (p, passage)

    # Escalate only candidate contradictions (where NLI confuses different moments of one story).
    suspect_keys: list[tuple[int, int]] = []
    suspect_pairs: list[tuple[str, str]] = []
    for (ci, pi), slot in best.items():
        entail, _ = slot[ENTAIL]
        contra, passage = slot[CONTRADICT]
        decision = calibrate_choice(
            {
                "supports": entail,
                "contradicts": contra,
                "not_addressed": max(0.0, 1.0 - max(entail, contra)),
            }
        )
        if contra >= S1_SUSPECT_CONTRA and (decision.choice == "contradicts" or decision.abstain):
            suspect_keys.append((ci, pi))
            suspect_pairs.append((claims[ci].text, passage))

    verified: dict[tuple[int, int], str | None] = {}
    if suspect_pairs and cascade is not None:
        for key, answer in zip(suspect_keys, cascade(suspect_pairs), strict=True):
            verified[key] = answer

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
            verdict = verified.get((ci, pi))
            if verdict == "contradicts":
                contradicting.append((pi, passage))
            elif verdict == "supports":
                supporting.append(pi)
            elif verdict == "not_addressed":
                if entail >= DECISIVE and entail > contra:
                    supporting.append(pi)
            elif contra >= CONTRADICTION and contra > entail:
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
    implied_claims: Sequence[str] = (),
) -> list[Evidence]:
    """Fact-checks from the document's own outlet are skipped: when the document is a
    fact-check, its own review of the claim it debunks is not evidence against it.

    Matches verbatim `claims` first and falls back to `implied_claims`
    (`plans/persuasion-analysis.md` P-L3); an implied claim has no span in the document, so its
    evidence cites only `check`.
    """
    checks = [
        c
        for c in context
        if c.fact_check is not None and (own_outlet is None or c.outlet != own_outlet)
    ]
    candidates: list[tuple[str, Span | None]] = [(c.text, c.span) for c in claims] + [
        (text.strip(), None) for text in implied_claims if text and text.strip()
    ]
    if not candidates or not checks:
        return []
    pairs = []
    for check in checks:
        assert check.fact_check is not None
        for text, _ in candidates:
            pairs += [(check.fact_check.claim, text), (text, check.fact_check.claim)]
    probabilities = nli(pairs)[:, ENTAIL].reshape(len(checks), len(candidates), 2).max(axis=2)
    n_verbatim = len(claims)

    def _direct_match(k: int, start: int, end: int) -> int | None:
        assert checks[k].fact_check is not None
        reviewed = checks[k].fact_check.claim
        passing = [
            (max(float(probabilities[k, j]), _overlap_score(reviewed, candidates[j][0])), j)
            for j in range(start, end)
            if probabilities[k, j] >= FACT_CHECK_ENTAIL
            or _overlap_score(reviewed, candidates[j][0]) >= FACT_CHECK_OVERLAP
        ]
        return max(passing, key=lambda item: item[0])[1] if passing else None

    evidence = []
    for k, check in enumerate(checks):
        assert check.fact_check is not None
        signal = rating_signal(check.fact_check.rating)
        if signal is None:
            continue
        j = _direct_match(k, 0, n_verbatim)
        if j is None:
            j = _direct_match(k, n_verbatim, len(candidates))
        verdict_quote: str | None = None
        if j is None:
            if signal[0] not in {"rated_false", "rated_misleading"}:
                continue
            matched = _verdict_match(
                check, [text for text, _ in candidates], nli, n_verbatim=n_verbatim
            )
            if matched is None:
                continue
            j, verdict_quote = matched
        _, span = candidates[j]
        rating = check.fact_check.rating
        publisher = check.fact_check.publisher or check.outlet or "A fact-checker"
        quote = (
            verdict_quote
            if verdict_quote and verdict_quote in check.text
            else (rating if rating in check.text else None)
        )
        what = "this claim" if span is not None else "an implied claim"
        refs = (
            [DocumentRef(kind="document", span=span), context_ref(check, quote)]
            if span is not None
            else [context_ref(check, quote)]
        )
        evidence.append(
            Evidence(
                id=next_id(),
                family=Family.fact_checks,
                signal=signal[0],
                value=signal[1],
                detail=f"{publisher} rated {what} “{rating}”.",
                source_refs=refs,
            )
        )
    return evidence


def _verdict_match(
    check: ContextItem,
    claim_texts: Sequence[str],
    nli: Nli,
    *,
    n_verbatim: int = 0,
) -> tuple[int, str] | None:
    """`(claim_index, verdict_passage)` when a passage of `check` debunks both the reviewed
    claim (`>= DECISIVE` two-way contradiction) and a candidate claim (`>= CONTRADICTION`
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
    if not candidates or not claim_texts:
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
    pairs = [(v, text) for v in verdicts for text in claim_texts]
    forward = nli(pairs)
    suspects = [i for i, probs in enumerate(forward) if probs[CONTRADICT] >= CONTRADICTION]
    if not suspects:
        return None
    backward = nli([(pairs[i][1], pairs[i][0]) for i in suspects])
    best_verbatim: tuple[float, int, str] | None = None
    best_any: tuple[float, int, str] | None = None
    for i, probs in zip(suspects, backward, strict=True):
        both = min(float(forward[i, CONTRADICT]), float(probs[CONTRADICT]))
        if both < CONTRADICTION:
            continue
        claim_idx = i % len(claim_texts)
        hit = (both, claim_idx, pairs[i][0])
        if claim_idx < n_verbatim and (best_verbatim is None or both > best_verbatim[0]):
            best_verbatim = hit
        if best_any is None or both > best_any[0]:
            best_any = hit
    chosen = best_verbatim or best_any
    return (chosen[1], chosen[2]) if chosen else None


def _overlap_score(a: str, b: str) -> float:
    return min(overlap(a, b), overlap(b, a))
