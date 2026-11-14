"""Story assignment with a stand-in embedder: threshold, date window, reasons, inputs."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from pipeline.common.contracts import ContextItem, Document, FactCheck
from pipeline.common.fixtures import example_analysis
from pipeline.story.assign import (
    CROSS_LANGUAGE_THRESHOLD,
    LEAD_CHARS,
    SAME_LANGUAGE_THRESHOLD,
    WINDOW_DAYS,
    assign,
    story_text,
    threshold_for,
)

DAY = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)


def unit(similarity: float) -> np.ndarray:
    """A unit vector whose dot product with [1, 0] is `similarity`."""
    return np.array([similarity, np.sqrt(max(0.0, 1 - similarity**2))], dtype=np.float32)


class Embedder:
    """Maps a text to a vector by the similarity written in it: `sim=0.9 ...`."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, texts: list[str]) -> np.ndarray:
        self.calls.append(texts)
        rows = [np.array([1.0, 0.0], dtype=np.float32)]  # the document
        for text in texts[1:]:
            rows.append(unit(float(text.split("sim=")[1].split()[0])))
        return np.stack(rows)


def item(i: int, sim: float, published: datetime | None = DAY, **kw) -> ContextItem:
    return ContextItem(
        id=f"ctx{i}",
        url=f"https://outlet{i}.example/a",
        outlet=f"outlet{i}.example",
        published_at=published,
        title=f"Report {i}",
        text=f"sim={sim} body of report {i}.",
        retrieved_by="feeds",
        tracking_ids=[],
        **kw,
    )


def analysis(*items: ContextItem, document_date: datetime | None = DAY):
    a = example_analysis()
    a.document = Document(
        url=None,
        outlet=None,
        published_at=document_date,
        title="The article",
        paragraphs=["First paragraph.", "Second paragraph."],
        outbound_links=[],
        tracking_ids=[],
    )
    a.context = list(items)
    return a


def test_threshold_decides_and_every_item_gets_an_assignment():
    embed = Embedder()
    patch = assign(analysis(item(1, 0.95), item(2, SAME_LANGUAGE_THRESHOLD), item(3, 0.80)), embed)
    assert [a.context_id for a in patch.assignments] == ["ctx1", "ctx2", "ctx3"]
    assert [a.in_story for a in patch.assignments] == [True, True, False]
    assert [a.similarity for a in patch.assignments] == pytest.approx(
        [0.95, SAME_LANGUAGE_THRESHOLD, 0.80]
    )
    assert patch.assignments[0].reason == "Covers the same event (similarity 0.950)"
    assert patch.assignments[2].reason == "About something else (similarity 0.800, below 0.900)"
    # One batch: the document first, then the items.
    assert len(embed.calls) == 1 and embed.calls[0][0] == story_text(
        "The article", "First paragraph.\nSecond paragraph."
    )


def test_reports_outside_the_date_window_are_out_whatever_their_similarity():
    late = DAY + timedelta(days=WINDOW_DAYS + 1)
    early = DAY - timedelta(days=30)
    edge = DAY - timedelta(days=WINDOW_DAYS)
    patch = assign(
        analysis(item(1, 0.99, late), item(2, 0.99, early), item(3, 0.99, edge)), Embedder()
    )
    assert [a.in_story for a in patch.assignments] == [False, False, True]
    assert patch.assignments[0].reason == (
        f"Published {WINDOW_DAYS + 1} days apart from the article, so not the same event"
    )
    assert patch.assignments[1].similarity == pytest.approx(0.99)  # still reported


def test_no_window_without_both_dates():
    undated_item = assign(analysis(item(1, 0.95, None)), Embedder())
    undated_document = assign(
        analysis(item(1, 0.95, DAY - timedelta(days=90)), document_date=None), Embedder()
    )
    assert undated_item.assignments[0].in_story is True
    assert undated_document.assignments[0].in_story is True


def test_fact_checks_are_exempt_from_the_window():
    check = FactCheck(claim="Wells will be banned", rating="False", publisher="Checker")
    old = item(1, 0.95, DAY - timedelta(days=200), fact_check=check)
    assert assign(analysis(old), Embedder()).assignments[0].in_story is True


def test_nothing_to_compare():
    embed = Embedder()
    assert assign(analysis(), embed).assignments == []
    a = analysis(item(1, 0.9))
    a.document = None
    assert assign(a, embed).assignments == []
    assert embed.calls == []  # no model call when there is nothing to compare


def test_story_text_is_headline_and_a_bounded_lead():
    body = "word " * 1000
    text = story_text("  Headline  ", body)
    assert text.startswith("Headline\nword word")
    assert len(text) == len("Headline\n") + LEAD_CHARS
    assert story_text(None, "Just  the\n\nbody") == "Just the body"
    assert story_text("", "Body") == "Body"


def test_the_patch_is_valid_for_the_api():
    from pipeline.common.contracts import StoryPatch

    patch = assign(analysis(item(1, 0.9), item(2, 0.5)), Embedder())
    assert StoryPatch.model_validate(patch.model_dump()) == patch
    assert all(isinstance(a.similarity, float) for a in patch.assignments)


def test_same_language_needs_the_stricter_threshold():
    # Between the two thresholds: a neighbouring event in the document's language stays out,
    # a report in another language on the same event gets in.
    sim = (SAME_LANGUAGE_THRESHOLD + CROSS_LANGUAGE_THRESHOLD) / 2
    a = analysis(item(1, sim, language="it"), item(2, sim, language="en"), item(3, sim))
    a.language.code = "it"
    patch = assign(a, Embedder())
    assert [x.in_story for x in patch.assignments] == [False, True, False]
    assert patch.assignments[0].reason.endswith("below 0.900)")
    # An item without a language is held to the stricter threshold.
    assert patch.assignments[2].reason.endswith("below 0.900)")


def test_threshold_for():
    assert threshold_for("it", "it") == SAME_LANGUAGE_THRESHOLD
    assert threshold_for("en", "it") == CROSS_LANGUAGE_THRESHOLD
    assert threshold_for(None, "it") == SAME_LANGUAGE_THRESHOLD
    assert threshold_for("en", None) == SAME_LANGUAGE_THRESHOLD


def test_no_document_language_means_the_stricter_threshold():
    a = analysis(item(1, 0.87, language="en"))
    a.language = None
    assert assign(a, Embedder()).assignments[0].in_story is False


# --- social media posts ----------------------------------------------------------------------


def as_post(i: int, retrieved_by: str, url: str) -> ContextItem:
    return item(i, 0.99).model_copy(update={"retrieved_by": retrieved_by, "url": url})


def test_a_social_media_post_is_never_coverage_however_similar():
    a = analysis(
        as_post(1, "bluesky", "https://bsky.app/profile/a/post/3kabc2defgh2x"),
        as_post(2, "oxylabs", "https://x.com/someone/status/1855000000000000000"),
        as_post(3, "mastodon", "https://m.example/@a/1234567"),
        item(4, 0.99),
    )
    by = {x.context_id: x for x in assign(a, Embedder()).assignments}
    for post_id in ("ctx1", "ctx2", "ctx3"):
        assert by[post_id].in_story is False
        assert by[post_id].reason.startswith("A social media post, not a news report")
        assert by[post_id].similarity == pytest.approx(0.99, abs=1e-3)  # still measured
    assert by["ctx4"].in_story is True


def test_a_page_whose_address_only_looks_like_a_mastodon_post_is_judged_as_a_report():
    a = analysis(as_post(1, "feeds", "https://paper.example/@desk/20261110"))
    assert assign(a, Embedder()).assignments[0].in_story is True
