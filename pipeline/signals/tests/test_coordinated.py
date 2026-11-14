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
