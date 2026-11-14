"""Offline unit tests for `pipeline.signals.rhetoric` (`P-L1`, no network or model downloads)."""

from itertools import count

from pipeline.common import spans
from pipeline.common.contracts import Document, DocumentRef, Family, Input, InputKind
from pipeline.common.fixtures import example_analysis
from pipeline.score.families import SINGLE
from pipeline.signals.rhetoric import (
    RaterAnswer,
    RaterItem,
    image_for_rater,
    rhetoric_evidence,
    rhetoric_family,
)

TINY_DATA_URI = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def ids():
    return (f"s{n}" for n in count(1)).__next__


def target_family() -> Family:
    return rhetoric_family() or Family.techniques


def meme_analysis():
    analysis = example_analysis()
    analysis.input = Input(
        kind=InputKind.image,
        value=TINY_DATA_URI,
        context_url="https://www.reddit.com/r/Conservative/comments/example/affordability/",
    )
    analysis.document = Document(
        url="https://www.reddit.com/r/Conservative/comments/example/affordability/",
        outlet="reddit.com",
        title="Affordability agenda in action",
        paragraphs=[
            "AFFORDABILITY",
            "TRUMP INVESTIGATIONS",
            "I THOUGHT THIS WAS ABOUT MY GROCERY BILL",
            'A reporter wrote that critics shouted "shameful betrayal of voters" outside.',
            "[Visual context] Cartoon showing a podium labelled AFFORDABILITY hidden behind a "
            "tall stack of papers labelled TRUMP INVESTIGATIONS while a shopper holds groceries.",
        ],
        outbound_links=[],
        tracking_ids=[],
    )
    return analysis


def test_non_verbatim_and_quoted_only_items_are_dropped_and_visual_cites_visual_paragraph() -> None:
    analysis = meme_analysis()
    assert analysis.document is not None
    seen_inputs: list[tuple[str, str | None]] = []

    def fake_rater(text: str, img: str | None) -> RaterAnswer:
        seen_inputs.append((text, img))
        return RaterAnswer(
            items=[
                # 1. Non-verbatim paraphrase -> MUST be dropped.
                RaterItem(
                    category="call",
                    technique="Slogans",
                    strength="clear",
                    kind="text",
                    quote="I thought this was about groceries",
                ),
                # 2. Quote inside `[Visual context]` -> MUST be dropped as a text quote.
                RaterItem(
                    category="simplification",
                    technique="Causal_Oversimplification",
                    strength="clear",
                    kind="text",
                    quote="tall stack of papers labelled TRUMP INVESTIGATIONS",
                ),
                # 3. Quoted speech only (`"shameful betrayal of voters"`) -> MUST be dropped.
                RaterItem(
                    category="manipulative_wording",
                    technique="Loaded_Language",
                    strength="clear",
                    kind="text",
                    quote="shameful betrayal of voters",
                ),
                # 4. Valid visual-only move -> cites the `[Visual context]` paragraph (index 4).
                RaterItem(
                    category="distraction",
                    technique="Straw_Man",
                    strength="clear",
                    kind="visual",
                    visual_element='podium "AFFORDABILITY" buried behind TRUMP INVESTIGATIONS',
                ),
                # 5. Valid text move (`weak` -> 0.5) -> cites exact verbatim span in paragraph 2.
                RaterItem(
                    category="attack_on_reputation",
                    technique="Appeal_to_Hypocrisy",
                    strength="weak",
                    kind="text",
                    quote="I THOUGHT THIS WAS ABOUT MY GROCERY BILL",
                ),
            ]
        )

    evidence = rhetoric_evidence(analysis, fake_rater, ids(), family=target_family())
    assert len(seen_inputs) == 1
    assert seen_inputs[0][1] == TINY_DATA_URI

    # Only the valid `clear` visual distraction (1.0) and `weak` text attack (0.5) survive,
    # ordered strongest first.
    assert [(e.signal, e.value) for e in evidence] == [
        ("distraction", 1.0),
        ("attack_on_reputation", 0.5),
    ]

    visual_ev, text_ev = evidence
    assert "visual description" in visual_ev.detail
    assert '"' not in visual_ev.detail  # no double quotes that could fail API quotation checks
    [vis_ref] = visual_ev.source_refs
    vis_doc_ref = vis_ref.root if hasattr(vis_ref, "root") else vis_ref
    assert isinstance(vis_doc_ref, DocumentRef)
    assert vis_doc_ref.span.paragraph == 4

    [txt_ref] = text_ev.source_refs
    txt_doc_ref = txt_ref.root if hasattr(txt_ref, "root") else txt_ref
    assert isinstance(txt_doc_ref, DocumentRef)
    assert spans.text_at(analysis.document, txt_doc_ref.span) == (
        "I THOUGHT THIS WAS ABOUT MY GROCERY BILL"
    )


def test_image_url_sends_no_data_uri_and_unavailable_model_returns_empty() -> None:
    analysis = meme_analysis()
    analysis.input = Input(kind=InputKind.image, value="https://i.redd.it/example.png")
    assert image_for_rater(analysis) is None
    assert rhetoric_evidence(analysis, lambda _t, _i: None, ids(), family=target_family()) == []


def test_satire_meme_skips_rhetoric_and_phase1_keeps_rhetoric_out_of_single() -> None:
    analysis = meme_analysis()
    assert analysis.document is not None
    analysis.document.paragraphs[-1] = "[Satire/humour meme] Pure joke reaction meme."
    called = []
    assert (
        rhetoric_evidence(
            analysis,
            lambda t, i: called.append((t, i)) or RaterAnswer(),
            ids(),
            family=target_family(),
        )
        == []
    )
    assert called == []

    # Phase 1 gate (Rule 1): `rhetoric` must NOT be in `families.SINGLE` before Phase 2 refit.
    if (rf := rhetoric_family()) is not None:
        assert rf not in SINGLE
