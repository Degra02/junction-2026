"""Coordinated signals on the example analysis: two copying sites sharing an analytics ID."""

from datetime import timedelta

from pipeline.common.contracts import ContextRef, DocumentRef, Family, OutletType
from pipeline.common.fixtures import example_analysis
from pipeline.signals.coordinated import find_copies, run_coordinated


def by_signal(analysis):
    return {e.signal: e for e in run_coordinated(analysis).evidence}


def test_example_copies_timing_and_shared_id() -> None:
    analysis = example_analysis()
    assert [c.id for c in find_copies(analysis)] == ["ctx2", "ctx3"]
    evidence = run_coordinated(analysis).evidence
    assert [e.id for e in evidence] == ["c1", "c2", "c3", "c4"]
    signals = {e.signal: e for e in evidence}
    reuse = signals["copied_passages"]
    assert (reuse.family, reuse.value) == (Family.text_reuse, 2.0)
    assert analysis.document is not None
    doc_ref = reuse.source_refs[0].root
    assert isinstance(doc_ref, DocumentRef)
    quoted = analysis.document.paragraphs[doc_ref.span.paragraph][
        doc_ref.span.start : doc_ref.span.end
    ]
    texts = {c.id: c.text for c in analysis.context}
    for ref in reuse.source_refs[1:]:
        assert isinstance(ref.root, ContextRef)
        assert ref.root.quote == quoted and quoted in texts[ref.root.id]
    timing = signals["copies_within_window"]
    assert timing.value == 2.0 and "51 minutes of the article" in timing.detail
    shared = signals["shared_tracking_id"]
    assert shared.value == 2.0 and "G-TRUTH12345" in shared.detail
    assert signals["young_copying_domains"].value == 2.0
    assert "listed_domain" not in signals


def test_wire_copy_is_syndication_not_coordination() -> None:
    analysis = example_analysis()
    # When patriot-voice is a news agency, it is not a copier, and ctx3 only repeats what the
    # agency published: syndication, so nothing counts as coordinated copying.
    profile = next(s for s in analysis.sources if s.domain == "patriot-voice.example")
    profile.outlet_type = OutletType.wire_service
    assert find_copies(analysis) == []


def test_document_that_only_repeats_wire_copy_has_no_reuse() -> None:
    analysis = example_analysis()
    assert analysis.document is not None
    wire = next(c for c in analysis.context if c.id == "ctx1")
    analysis.document.paragraphs = [wire.text]
    for item in analysis.context:
        if item.id in {"ctx2", "ctx3"}:
            item.text = wire.text
    assert find_copies(analysis) == []
    assert "copied_passages" not in by_signal(analysis)


def test_copies_far_apart_are_not_timed_together() -> None:
    analysis = example_analysis()
    for item in analysis.context:
        if item.published_at is not None:
            item.published_at += timedelta(days=3)
    assert "copies_within_window" not in by_signal(analysis)


def test_pasted_text_without_ids_uses_ids_shared_by_copies() -> None:
    analysis = example_analysis()
    assert analysis.document is not None
    analysis.document.tracking_ids = []
    analysis.document.published_at = None
    signals = by_signal(analysis)
    assert signals["shared_tracking_id"].value == 2.0
    assert "the same analytics ID" in signals["shared_tracking_id"].detail
    assert "of each other" in signals["copies_within_window"].detail


def test_listed_outlet_is_a_known_network() -> None:
    analysis = example_analysis()
    analysis.sources[0].known_network = "portal_kombat"
    item = by_signal(analysis)["listed_domain"]
    assert (item.family, item.value) == (Family.known_networks, 1.0)
    assert "portal kombat" in item.detail


def test_no_document_no_evidence() -> None:
    analysis = example_analysis()
    analysis.document = None
    assert run_coordinated(analysis).evidence == []


def test_established_newsrooms_repeating_one_text_are_syndication() -> None:
    # Agency copy whose agency item was not retrieved: national and local outlets republishing
    # the same text are not a network.
    analysis = example_analysis()
    for domain in ("patriot-voice.example", "free-nation-news.example"):
        profile = next(s for s in analysis.sources if s.domain == domain)
        profile.outlet_type = OutletType.national if domain[0] == "p" else OutletType.local
    assert find_copies(analysis) == []


def test_fact_check_quoting_the_hoax_is_not_a_copy() -> None:
    analysis = example_analysis()
    assert analysis.document is not None
    hoax = analysis.document.paragraphs
    analysis.document.outlet = "factcheck.example"
    analysis.document.paragraphs = [
        f"Claim: “{hoax[0]}”",
        f"Several websites added that “{hoax[1]}”",
        "Verdict: False. The draft law requires registration by 2028 and bans nothing.",
    ]
    assert find_copies(analysis) == []


def test_satire_outlet_is_not_a_copier() -> None:
    analysis = example_analysis()
    for domain in ("patriot-voice.example", "free-nation-news.example"):
        next(s for s in analysis.sources if s.domain == domain).outlet_type = OutletType.satire
    assert find_copies(analysis) == []


def test_sister_language_edition_in_story_counts_toward_known_network() -> None:
    analysis = example_analysis()
    # Clear verbatim copies: ctx2 is now a French translation covering the same story.
    analysis.sources[0].known_network = "portal_kombat"
    next(
        s for s in analysis.sources if s.domain == "patriot-voice.example"
    ).known_network = "portal_kombat"
    for item in analysis.context:
        if item.id == "ctx2":
            item.text = "Le gouvernement interdira les puits privés dès janvier selon ce texte."
            item.in_story = True
        elif item.id == "ctx3":
            item.text = "Unrelated text with no shared phrases."
            item.in_story = False
    assert find_copies(analysis) == []
    listed = by_signal(analysis)["listed_domain"]
    assert listed.value == 2.0 and "2 sites involved" in listed.detail

    # Pasted text (no document outlet) still catches the listed sister site in the story.
    assert analysis.document is not None
    analysis.document.outlet = None
    pasted_listed = by_signal(analysis)["listed_domain"]
    assert pasted_listed.value == 1.0 and "Another site covering the story" in pasted_listed.detail


def test_mainstream_article_is_not_flagged_by_listed_outlet_in_same_story() -> None:
    analysis = example_analysis()
    assert analysis.document is not None
    analysis.document.outlet = "newswire.example"
    # ctx2 is a Pravda-listed site covering the same news event, not copying the wire text.
    next(
        s for s in analysis.sources if s.domain == "patriot-voice.example"
    ).known_network = "portal_kombat"
    for item in analysis.context:
        if item.id == "ctx2":
            item.text = "Un autre article sur le même événement diplomatique sans copie."
            item.in_story = True
            item.similarity = 0.88
        elif item.id == "ctx3":
            item.text = "Unrelated."
            item.in_story = False
    assert find_copies(analysis) == []
    assert "listed_domain" not in by_signal(analysis)

    # Same for an untyped outlet and for pasted text below near-duplicate similarity (0.93).
    analysis.document.outlet = "untyped-blog.example"
    assert "listed_domain" not in by_signal(analysis)
    analysis.document.outlet = None
    assert "listed_domain" not in by_signal(analysis)
