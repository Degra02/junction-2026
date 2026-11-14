"""Single-actor families on the example analysis, with stand-ins for the models."""

from itertools import count

import numpy as np
import pytest

from pipeline.common.contracts import Analysis, ContextRef, DocumentRef, Evidence, Family
from pipeline.common.fixtures import example_analysis
from pipeline.signals.claims import (
    claim_support_evidence,
    fact_check_evidence,
    rating_signal,
)
from pipeline.signals.source_profile import source_profile_evidence
from pipeline.signals.techniques import CATEGORIES, technique_evidence, tone_evidence
from pipeline.signals.text import chunks, sentence_windows, story_peers

LABELS = [t for _, techniques in CATEGORIES.values() for t in techniques]


def ids():
    return (f"s{n}" for n in count(1)).__next__


def fake_nli(pairs: list[tuple[str, str]]) -> np.ndarray:
    """Contradiction when the premise denies a ban the hypothesis states; entailment on equality."""
    out = []
    for premise, hypothesis in pairs:
        if "does not ban" in premise and "ban" in hypothesis:
            out.append([0.02, 0.08, 0.9])
        elif premise.strip(". ").casefold() == hypothesis.strip(". ").casefold():
            out.append([0.95, 0.04, 0.01])
        else:
            out.append([0.1, 0.8, 0.1])
    return np.array(out, dtype=np.float32)


def assert_refs_valid(analysis: Analysis, evidence: list[Evidence]) -> None:
    """What the API checks: spans inside their paragraph, quotes verbatim in the context item."""
    assert analysis.document is not None
    context = {c.id: c for c in analysis.context}
    for item in evidence:
        assert item.source_refs
        for ref in item.source_refs:
            ref = ref.root if hasattr(ref, "root") else ref
            if isinstance(ref, DocumentRef):
                paragraph = analysis.document.paragraphs[ref.span.paragraph]
                assert 0 <= ref.span.start < ref.span.end <= len(paragraph)
            elif isinstance(ref, ContextRef):
                assert ref.id in context
                assert ref.quote is None or ref.quote in context[ref.id].text


def test_peers_exclude_copies_fact_checks_unrelated_items_and_own_outlet() -> None:
    analysis = example_analysis()
    # ctx2/ctx3 copy the document, ctx4 is a fact-check, ctx5 is out of the story.
    assert [p.id for p in story_peers(analysis, 10)] == ["ctx1"]
    copy = next(c for c in analysis.context if c.id == "ctx2")
    assert analysis.document is not None
    copy.text = analysis.document.paragraphs[2] + " The rest is new reporting."
    # One of the document's four sentences is a quote, not a copy.
    assert [p.id for p in story_peers(analysis, 10)] == ["ctx2", "ctx1"]


def test_passages_are_exact_substrings() -> None:
    text = "First sentence here. Second one!  Third?\nA line without a stop\n" + "x " * 300
    pieces = chunks(text, max_chars=35)
    assert pieces[:3] == ["First sentence here. Second one!", "Third?", "A line without a stop"]
    assert all(piece in text for piece in pieces)
    windows = sentence_windows("One. Two!  Three?")
    assert windows == ["One. Two!", "Two!  Three?"]
    assert sentence_windows(" Only one. ") == ["Only one."]


def test_claim_contradicted_by_independent_report() -> None:
    analysis = example_analysis()
    evidence = claim_support_evidence(analysis.claims, story_peers(analysis, 10), fake_nli, ids())
    # Claim 2 is in ctx1 word for word, so only claim 1 is judged.
    [contradicted] = evidence
    assert contradicted.source_refs[0].root.span == analysis.claims[0].span
    assert (contradicted.family, contradicted.signal) == (Family.claim_support, "contradicted")
    assert contradicted.value == 1.0
    assert "1 of the 1 sources" in contradicted.detail
    [quote] = [r.root for r in contradicted.source_refs if isinstance(r.root, ContextRef)]
    assert quote.id == "ctx1"
    assert quote.quote is not None and "The draft does not ban private wells." in quote.quote
    assert_refs_valid(analysis, evidence)


def test_claim_nobody_addresses_is_unaddressed() -> None:
    analysis = example_analysis()
    peers = [c for c in analysis.context if c.id == "ctx5"] * 3
    [item] = claim_support_evidence(analysis.claims[:1], peers, fake_nli, ids())
    assert (item.signal, item.value) == ("unaddressed", 1.0)
    assert "None of the 3" in item.detail


def test_fact_check_matches_claim_and_maps_rating() -> None:
    analysis = example_analysis()
    evidence = fact_check_evidence(analysis.claims, analysis.context, fake_nli, ids())
    assert len(evidence) == 1
    [item] = evidence
    assert (item.family, item.signal, item.value) == (Family.fact_checks, "rated_false", 1.0)
    assert item.source_refs[0].root.span == analysis.claims[0].span
    assert item.source_refs[1].root.quote == "False"
    assert_refs_valid(analysis, evidence)


def test_unrelated_fact_check_is_not_matched() -> None:
    analysis = example_analysis()
    check = next(c for c in analysis.context if c.fact_check is not None)
    assert check.fact_check is not None
    check.fact_check.claim = "The cup final was decided by penalties"
    assert fact_check_evidence(analysis.claims, analysis.context, fake_nli, ids()) == []


@pytest.mark.parametrize(
    ("rating", "signal"),
    [
        ("False", "rated_false"),
        ("Falso", "rated_false"),
        ("Pants on Fire!", "rated_false"),
        ("Inaccurate", "rated_false"),
        ("Not true", "rated_false"),
        ("Mostly False", "rated_misleading"),
        ("Half True", "rated_misleading"),
        ("Fuorviante", "rated_misleading"),
        ("Mostly true", "rated_true"),
        ("Vero", "rated_true"),
        ("Severo giudizio", None),
        ("Satire", None),
    ],
)
def test_rating_vocabulary(rating: str, signal: str | None) -> None:
    found = rating_signal(rating)
    assert (found[0] if found else None) == signal


def test_techniques_aggregate_to_categories_with_paragraph_refs() -> None:
    analysis = example_analysis()
    assert analysis.document is not None
    paragraphs = analysis.document.paragraphs
    probs = np.full((3, len(LABELS)), 0.1, dtype=np.float32)
    probs[1, LABELS.index("Name_Calling-Labeling")] = 0.9
    probs[1, LABELS.index("Loaded_Language")] = 0.8
    probs[0, LABELS.index("Loaded_Language")] = 0.6
    thresholds = np.full(len(LABELS), 0.5, dtype=np.float32)
    evidence = technique_evidence(paragraphs, [0, 1, 2], probs, LABELS, thresholds, ids())
    by_signal = {e.signal: e for e in evidence}
    assert set(by_signal) == {"attack_on_reputation", "manipulative_wording"}
    wording = by_signal["manipulative_wording"]
    assert wording.value == pytest.approx(0.8)
    assert [r.root.span.paragraph for r in wording.source_refs] == [1, 0]
    assert "in 2 paragraphs" in wording.detail
    assert by_signal["attack_on_reputation"].source_refs[0].root.span.end == len(paragraphs[1])
    assert [e.id for e in evidence] == ["s1", "s2"]


def test_tone_compares_with_peers_and_needs_three() -> None:
    analysis = example_analysis()
    assert analysis.document is not None
    paragraphs = analysis.document.paragraphs
    peers = analysis.context[:3]
    charged = np.array([0.7, 0.9, 0.2])
    [item] = tone_evidence(paragraphs, [0, 1, 2], charged, peers, [0.1, 0.2, 0.15], ids())
    assert item.value > 2
    assert item.detail.startswith("More emotionally charged than 3 of 3")
    assert item.source_refs[0].root.span.paragraph == 1
    calm = tone_evidence(paragraphs, [0, 1, 2], charged * 0, peers, [0.1, 0.2, 0.3], ids())
    assert calm[0].value < 0
    assert tone_evidence(paragraphs, [0, 1, 2], charged, peers[:2], [0.1, 0.2], ids()) == []


def test_source_profile_age_and_type() -> None:
    analysis = example_analysis()
    evidence = source_profile_evidence(analysis, ids())
    by_signal = {e.signal: e for e in evidence}
    assert by_signal["domain_age_days"].value == 15.0
    assert "registered 15 days before" in by_signal["domain_age_days"].detail
    assert "outlet_partisan" in by_signal


def test_source_profile_needs_an_outlet() -> None:
    analysis = example_analysis()
    assert analysis.document is not None
    analysis.document.outlet = None
    assert source_profile_evidence(analysis, ids()) == []
