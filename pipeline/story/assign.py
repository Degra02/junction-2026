"""Which context items cover the same event as the document: embeddings plus a date window.

Pure logic: the embedding function is passed in (`model.embed` in the stage, a stand-in in
tests), so this module loads no model.

Each item gets `similarity` (cosine of headline + lead embeddings, in [-1, 1]) and `in_story`:
- out when it was published more than `WINDOW_DAYS` from the document (when both dates are
  known); fact-checks are exempt, since a debunk may predate the article that repeats the claim;
- otherwise in when `similarity >= THRESHOLD`.

`THRESHOLD` was calibrated on Sat 14.11 on 22 live reports of 4 stories in it/en/de/es (the
Garante's fine on Meta, the US offer on Ukraine's NATO membership, COP31, Nvidia), with the
600-character lead that separated best: same-event pairs scored 0.841-0.970, other stories up to
0.834, same-topic different events (hard negatives) 0.833-0.882. At 0.845, 11 of 12 same-event
reports are kept, no other-story one, and 1 of 4 hard negatives. Missing a related report only
makes the score abstain sooner; counting an unrelated one as a peer would distort tone and claim
support, so the threshold leans to precision. Recalibrate on mosearc's labelled set.
"""

from collections.abc import Callable, Sequence
from datetime import datetime

import numpy as np

from pipeline.common.contracts import Analysis, ContextItem, StoryAssignment, StoryPatch

THRESHOLD = 0.845
WINDOW_DAYS = 7
LEAD_CHARS = 600

type Embed = Callable[[list[str]], np.ndarray]


def story_text(title: str | None, body: str) -> str:
    """Headline and lead: what decides which event a report is about."""
    lead = " ".join(body.split())[:LEAD_CHARS]
    return f"{title.strip()}\n{lead}" if title and title.strip() else lead


def _days_apart(a: datetime | None, b: datetime | None) -> int | None:
    if a is None or b is None:
        return None
    return abs((a - b).days)


def _assignment(
    item: ContextItem, similarity: float, document_date: datetime | None
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
    if similarity >= THRESHOLD:
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
        reason=f"About something else (similarity {similarity:.3f}, below {THRESHOLD:.3f})",
    )


def assign(analysis: Analysis, embed: Embed) -> StoryPatch:
    """One assignment per context item, in context order."""
    context: Sequence[ContextItem] = analysis.context
    document = analysis.document
    if not context or document is None or not document.paragraphs:
        return StoryPatch(assignments=[])
    texts = [story_text(document.title, "\n".join(document.paragraphs))]
    texts += [story_text(item.title, item.text) for item in context]
    vectors = embed(texts)
    similarities = vectors[1:] @ vectors[0]
    return StoryPatch(
        assignments=[
            _assignment(item, float(sim), document.published_at)
            for item, sim in zip(context, similarities, strict=True)
        ]
    )
