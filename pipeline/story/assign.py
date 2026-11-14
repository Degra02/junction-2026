"""Which context items cover the same event as the document: embeddings plus a date window.

Pure logic: the embedding function is passed in (`model.embed` in the stage, a stand-in in
tests), so this module loads no model.

Each item gets `similarity` (cosine of headline + lead embeddings, in [-1, 1]) and `in_story`:
- out when it was published more than `WINDOW_DAYS` from the document (when both dates are
  known); fact-checks are exempt, since a debunk may predate the article that repeats the claim;
- otherwise in when `similarity` reaches the threshold for the pair: `SAME_LANGUAGE_THRESHOLD`
  when item and document are in the same language (or either language is unknown),
  `CROSS_LANGUAGE_THRESHOLD` otherwise.

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
"""

from collections.abc import Callable, Sequence
from datetime import datetime

import numpy as np

from pipeline.common.contracts import Analysis, ContextItem, StoryAssignment, StoryPatch

SAME_LANGUAGE_THRESHOLD = 0.90
CROSS_LANGUAGE_THRESHOLD = 0.845
WINDOW_DAYS = 7
LEAD_CHARS = 600

type Embed = Callable[[list[str]], np.ndarray]


def story_text(title: str | None, body: str) -> str:
    """Headline and lead: what decides which event a report is about."""
    lead = " ".join(body.split())[:LEAD_CHARS]
    return f"{title.strip()}\n{lead}" if title and title.strip() else lead


def threshold_for(item_language: str | None, document_language: str | None) -> float:
    """The stricter same-language threshold unless both languages are known and differ."""
    if item_language and document_language and item_language != document_language:
        return CROSS_LANGUAGE_THRESHOLD
    return SAME_LANGUAGE_THRESHOLD


def _days_apart(a: datetime | None, b: datetime | None) -> int | None:
    if a is None or b is None:
        return None
    return abs((a - b).days)


def _assignment(
    item: ContextItem,
    similarity: float,
    document_date: datetime | None,
    document_language: str | None,
) -> StoryAssignment:
    similarity = round(similarity, 4)
    apart = _days_apart(item.published_at, document_date)
    if item.fact_check is None and apart is not None and apart > WINDOW_DAYS:
        return StoryAssignment(
            context_id=item.id,
            similarity=similarity,
            in_story=False,
            reason=f"Published {apart} days apart from the article, so not the same event",
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


def assign(analysis: Analysis, embed: Embed) -> StoryPatch:
    """One assignment per context item, in context order."""
    context: Sequence[ContextItem] = analysis.context
    document = analysis.document
    if not context or document is None or not document.paragraphs:
        return StoryPatch(assignments=[])
    language = analysis.language.code if analysis.language else None
    texts = [story_text(document.title, "\n".join(document.paragraphs))]
    texts += [story_text(item.title, item.text) for item in context]
    vectors = embed(texts)
    similarities = vectors[1:] @ vectors[0]
    return StoryPatch(
        assignments=[
            _assignment(item, float(sim), document.published_at, language)
            for item, sim in zip(context, similarities, strict=True)
        ]
    )
