"""Which context items cover the same event as the document: embeddings, a date window and, in
the similarity grey zone, the language model's same-event check.

Pure logic: the embedding function and the same-event check are passed in (`model.embed` and
`judge.same_event` in the stage, stand-ins in tests), so this module loads no model and makes
no call.

Each item gets `similarity` (cosine of headline + lead embeddings, in [-1, 1]) and `in_story`:
- out when it was published more than `WINDOW_DAYS` from the document (when both dates are
  known); fact-checks are exempt, since a debunk may predate the article that repeats the claim;
- otherwise, when `similarity` falls in the pair's grey zone (`grey_zone`) and the item is not
  a fact-check, in or out as the same-event check answers (at most `MAX_JUDGED` items per
  analysis, the most similar first);
- otherwise in when `similarity` reaches the threshold for the pair: `SAME_LANGUAGE_THRESHOLD`
  when item and document are in the same language (or either language is unknown),
  `CROSS_LANGUAGE_THRESHOLD` otherwise. This is also the rule in the grey zone when the check
  gives no answer.

Why two thresholds: multilingual embeddings score same-language pairs higher than
cross-language pairs on the same content. With one threshold, same-language reports on a
neighbouring event (Russia's own NATO proposal, or a negotiation update, inside the story of the
US offer of NATO membership for the Donbas) got in, and claim support then found "contradictions"
between different events.

Calibrated on Sat 14.11 on 92 labelled pairs from live reports in it/en/de/es (the Garante's fine
on Meta, the US NATO offer twice, COP31, Nvidia), headline plus 600-character lead:
- same language: same event 0.858-0.970, different events up to 0.883;
- across languages: same event 0.842-0.896, different events up to 0.837.
At 0.90 / 0.845, 13 of 16 same-event reports are kept and none of 76 different-event ones (a
single 0.845 threshold let 5 in). The ones given up are broad summit coverage (COP31 side events)
and one cross-language report. Missing a related report only makes the score abstain sooner;
counting an unrelated one as a peer distorts tone and claim support, so both lean to precision.
Recalibrate on the labelled set when it has same-event pairs.

The grey zones bracket the overlap above (same language 0.85-0.93, across languages
0.80-0.88): there the thresholds give up broad same-event coverage on one side and risk a
neighbouring event on the other, and a headline-and-lead comparison by the language model
separates the two. Above the zone a report is in, below it out, with no call.
"""

from collections.abc import Callable, Sequence
from datetime import datetime

import numpy as np

from pipeline.common.contracts import Analysis, ContextItem, StoryAssignment, StoryPatch
from pipeline.signals.systemone import BinaryDecision, calibrate_binary

SAME_LANGUAGE_THRESHOLD = 0.90
CROSS_LANGUAGE_THRESHOLD = 0.845
SAME_LANGUAGE_GREY_ZONE = (0.85, 0.93)
CROSS_LANGUAGE_GREY_ZONE = (0.80, 0.88)
MAX_JUDGED = 20
WINDOW_DAYS = 7
LEAD_CHARS = 600

type Embed = Callable[[list[str]], np.ndarray]
# `(article, reports) -> answer per report`: True same event, False not, None no answer.
type Judge = Callable[[str, list[str]], list[bool | None]]


def story_text(title: str | None, body: str) -> str:
    """Headline and lead: what decides which event a report is about."""
    lead = " ".join(body.split())[:LEAD_CHARS]
    return f"{title.strip()}\n{lead}" if title and title.strip() else lead


def threshold_for(item_language: str | None, document_language: str | None) -> float:
    """The stricter same-language threshold unless both languages are known and differ."""
    if item_language and document_language and item_language != document_language:
        return CROSS_LANGUAGE_THRESHOLD
    return SAME_LANGUAGE_THRESHOLD


def grey_zone(item_language: str | None, document_language: str | None) -> tuple[float, float]:
    """`[low, high)` similarity band where the same-event check decides, by the same language
    rule as `threshold_for`."""
    if item_language and document_language and item_language != document_language:
        return CROSS_LANGUAGE_GREY_ZONE
    return SAME_LANGUAGE_GREY_ZONE


def _days_apart(a: datetime | None, b: datetime | None) -> int | None:
    if a is None or b is None:
        return None
    return abs((a - b).days)


def _outside_window(item: ContextItem, document_date: datetime | None) -> int | None:
    """Days between item and document when that rules the item out, else None."""
    apart = _days_apart(item.published_at, document_date)
    if item.fact_check is None and apart is not None and apart > WINDOW_DAYS:
        return apart
    return None


def story_decision(
    item: ContextItem, similarity: float, document_language: str | None
) -> BinaryDecision:
    """System-One `noul` decision from cosine similarity, marking grey-zone reports `abstain`."""
    decision = calibrate_binary(
        similarity,
        threshold=threshold_for(item.language, document_language),
        grey_zone=grey_zone(item.language, document_language),
    )
    if item.fact_check is not None:
        return BinaryDecision(noul=decision.noul, confidence=decision.confidence, abstain=False)
    return decision


def _assignment(
    item: ContextItem,
    similarity: float,
    document_date: datetime | None,
    document_language: str | None,
    same_event: bool | None,
) -> StoryAssignment:
    similarity = round(similarity, 4)
    apart = _outside_window(item, document_date)
    if apart is not None:
        return StoryAssignment(
            context_id=item.id,
            similarity=similarity,
            in_story=False,
            reason=f"Published {apart} days apart from the article, so not the same event",
        )
    if same_event is not None:
        verdict = "Covers the same event" if same_event else "About a different event"
        return StoryAssignment(
            context_id=item.id,
            similarity=similarity,
            in_story=same_event,
            reason=f"{verdict}, by headline and lead (similarity {similarity:.3f})",
        )
    threshold = threshold_for(item.language, document_language)
    if similarity >= threshold:
        return StoryAssignment(
            context_id=item.id,
            similarity=similarity,
            in_story=True,
            reason=f"Covers the same event (similarity {similarity:.3f})",
        )
    return StoryAssignment(
        context_id=item.id,
        similarity=similarity,
        in_story=False,
        reason=f"About something else (similarity {similarity:.3f}, below {threshold:.3f})",
    )


def assign(analysis: Analysis, embed: Embed, judge: Judge) -> StoryPatch:
    """One assignment per context item, in context order."""
    context: Sequence[ContextItem] = analysis.context
    document = analysis.document
    if not context or document is None or not document.paragraphs:
        return StoryPatch(assignments=[])
    language = analysis.language.code if analysis.language else None
    texts = [story_text(document.title, "\n".join(document.paragraphs))]
    texts += [story_text(item.title, item.text) for item in context]
    vectors = embed(texts)
    similarities = [float(s) for s in vectors[1:] @ vectors[0]]

    decisions = [
        story_decision(item, sim, language) for item, sim in zip(context, similarities, strict=True)
    ]
    grey = [
        i
        for i, (item, decision) in enumerate(zip(context, decisions, strict=True))
        if _outside_window(item, document.published_at) is None and decision.abstain
    ]
    grey = sorted(grey, key=lambda i: -similarities[i])[:MAX_JUDGED]
    answers: list[bool | None] = [None] * len(context)
    if grey:
        for i, answer in zip(grey, judge(texts[0], [texts[i + 1] for i in grey]), strict=True):
            answers[i] = answer
    return StoryPatch(
        assignments=[
            _assignment(item, sim, document.published_at, language, answer)
            for item, sim, answer in zip(context, similarities, answers, strict=True)
        ]
    )
