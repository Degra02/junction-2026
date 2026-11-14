"""Single-actor families on the example analysis, with stand-ins for the models and the claim
check."""

from itertools import count

import numpy as np
import pytest

from pipeline.common.contracts import (
    Analysis,
    ContextRef,
    DocumentRef,
    Evidence,
    Family,
    OutletType,
)
from pipeline.common.fixtures import example_analysis
from pipeline.signals.claims import (
    claim_support_evidence,
    fact_check_evidence,
    rating_signal,
)
from pipeline.signals.source_profile import source_profile_evidence
from pipeline.signals.systemone import calibrate_binary, calibrate_choice, cascade_enabled
from pipeline.signals.techniques import CATEGORIES, technique_evidence, tone_evidence
from pipeline.signals.text import (
    chunks,
    mask_quotations,
    own_words,
    sentence_windows,
    story_peers,
)

LABELS = [t for _, techniques in CATEGORIES.values() for t in techniques]


def ids():
    return (f"s{n}" for n in count(1)).__next__


def fake_nli(pairs: list[tuple[str, str]]) -> np.ndarray:
    """Contradiction (either direction) between a text that denies a ban and one that states
    it; entailment on equality."""
    out = []
    for premise, hypothesis in pairs:
        denies = ["does not ban" in text for text in (premise, hypothesis)]
        if denies[0] != denies[1] and "ban" in premise and "ban" in hypothesis:
            out.append([0.02, 0.03, 0.95])
        elif premise.strip(". ").casefold() == hypothesis.strip(". ").casefold():
            out.append([0.95, 0.04, 0.01])
        else:
            out.append([0.1, 0.8, 0.1])
    return np.array(out, dtype=np.float32).reshape(-1, 3)


def one_way_nli(pairs: list[tuple[str, str]]) -> np.ndarray:
    """What NLI does on two moments of one story: high contradiction in one direction only."""
    return np.array(
        [
            [0.01, 0.01, 0.98] if "ban" in h and "does not ban" in p else [0.1, 0.8, 0.1]
            for p, h in pairs
        ],
        dtype=np.float32,
    ).reshape(-1, 3)


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
    next(
        s for s in analysis.sources if s.domain == "patriot-voice.example"
    ).outlet_type = OutletType.satire
    assert [p.id for p in story_peers(analysis, 10)] == ["ctx1"]
    # Two dispatches from the same outlet domain count as one independent peer, most similar first.
    dup = analysis.context[0].model_copy(
        update={"id": "ctx1b", "outlet": f"www.{analysis.context[0].outlet}", "similarity": 0.99}
    )
    analysis.context.append(dup)
    assert [p.id for p in story_peers(analysis, 10)] == ["ctx1b"]


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
    peers = story_peers(analysis, 10)
    seen_pairs: list[tuple[str, str]] = []

    def confirm(pairs):
        seen_pairs.extend(pairs)
        return ["contradicts"] * len(pairs)

    evidence = claim_support_evidence(analysis.claims, peers, fake_nli, ids(), cascade=confirm)
    # Claim 2 is in ctx1 word for word, so only claim 1 is judged; only its suspect pair escalates.
    assert len(seen_pairs) == 1
    [contradicted] = evidence
    assert contradicted.source_refs[0].root.span == analysis.claims[0].span
    assert (contradicted.family, contradicted.signal) == (Family.claim_support, "contradicted")
    assert contradicted.value == pytest.approx(2 / 3, abs=1e-3)
    assert "1 of the 1 sources" in contradicted.detail
    [quote] = [r.root for r in contradicted.source_refs if isinstance(r.root, ContextRef)]
    assert quote.id == "ctx1"
    assert quote.quote is not None and "The draft does not ban private wells." in quote.quote
    assert_refs_valid(analysis, evidence)


def test_cascade_vetoes_false_nli_contradiction_and_offline_falls_back_to_system1() -> None:
    analysis = example_analysis()
    peers = story_peers(analysis, 10)
    # Cascade vetoes a two-moment false contradiction ("not_addressed").
    veto = lambda pairs: ["not_addressed"] * len(pairs)  # noqa: E731
    assert claim_support_evidence(analysis.claims, peers, fake_nli, ids(), cascade=veto) == []
    # Offline / unavailable cascade (`None`) falls back to strict two-way System-1 NLI (>= 0.90).
    offline = claim_support_evidence(
        analysis.claims, peers, fake_nli, ids(), cascade=lambda pairs: [None] * len(pairs)
    )
    assert [e.signal for e in offline] == ["contradicted"]
    # One-way NLI contradiction is rejected locally by System 1 without calling cascade.
    called = []
    assert (
        claim_support_evidence(
            analysis.claims, peers, one_way_nli, ids(), cascade=lambda p: called.append(p) or []
        )
        == []
    )
    assert called == []


def test_claim_nobody_addresses_is_unaddressed() -> None:
    analysis = example_analysis()
    peers = [c for c in analysis.context if c.id == "ctx5"] * 3
    [item] = claim_support_evidence(analysis.claims[:1], peers, fake_nli, ids())
    assert (item.signal, item.value) == ("unaddressed", 1.0)
    assert "None of the 3" in item.detail


def test_systemone_calibration_and_tos_oauth_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    confident = calibrate_choice({"supports": 0.85, "contradicts": 0.05, "not_addressed": 0.10})
    assert (confident.choice, confident.abstain) == ("supports", False)
    assert sum(confident.probabilities.values()) == pytest.approx(1.0, abs=1e-3)

    uncertain = calibrate_choice({"supports": 0.44, "contradicts": 0.36, "not_addressed": 0.20})
    assert uncertain.abstain is True

    grey = calibrate_binary(0.88, threshold=0.90, grey_zone=(0.85, 0.93))
    assert grey.abstain is True and grey.yes is False
    clear = calibrate_binary(0.96, threshold=0.90, grey_zone=(0.85, 0.93))
    assert clear.abstain is False and clear.yes is True

    monkeypatch.setenv("LLM_API_KEY", "sk-ant-oat01-personal-token")
    assert cascade_enabled() is False
    monkeypatch.setenv("LLM_API_KEY", "sk-hstgr-router-key")
    monkeypatch.setenv("DECISION_CASCADE", "0")
    assert cascade_enabled() is False
    monkeypatch.setenv("DECISION_CASCADE", "1")
    assert cascade_enabled() is True


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


def test_a_fact_check_is_not_evidence_against_its_own_article() -> None:
    analysis = example_analysis()
    found = fact_check_evidence(
        analysis.claims, analysis.context, fake_nli, ids(), own_outlet="factcheck.example"
    )
    assert found == []


def test_cross_lingual_fact_check_matches_via_debunking_verdict() -> None:
    analysis = example_analysis()
    check = next(c for c in analysis.context if c.fact_check is not None)
    assert check.fact_check is not None
    # Reviewed claim is in German (no word overlap, no direct entailment in fake_nli), while the
    # verdict sentence "The draft does not ban private wells." contradicts both "ban" claims.
    check.fact_check.claim = "Die Regierung plant ein ban der Brunnen bis Januar"
    [matched] = fact_check_evidence(analysis.claims, analysis.context, fake_nli, ids())
    assert (matched.signal, matched.value) == ("rated_false", 1.0)
    assert matched.source_refs[0].root.span == analysis.claims[0].span
    assert_refs_valid(analysis, [matched])

    # A document asserting the true negation is agreed with, never matched as rated_false.
    assert analysis.document is not None
    analysis.document.paragraphs[0] = "The draft does not ban private wells."
    analysis.claims[0].text = "The draft does not ban private wells."
    analysis.claims[0].span.end = len(analysis.document.paragraphs[0])
    assert fact_check_evidence(analysis.claims[:1], analysis.context, fake_nli, ids()) == []


def test_quotations_are_masked_in_any_script() -> None:
    text = 'He called them “traitors”, «предатели» and „Verräter“ and said "they will burn".'
    assert mask_quotations(text) == 'He called them “…”, «…» and „…“ and said "…".'
    assert mask_quotations("It's the farmers' law, isn't it?") == "It's the farmers' law, isn't it?"


def test_a_text_that_is_all_quote_keeps_its_words() -> None:
    pasted = ["“The government will ban private wells by January. Share before they delete it!”"]
    assert own_words(pasted) == pasted
    report = ["The senator said “they are traitors” at a rally on Saturday afternoon in the city."]
    assert own_words(report) == [
        "The senator said “…” at a rally on Saturday afternoon in the city."
    ]


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
    # Share of the paragraphs with the technique, not the highest probability; three paragraphs
    # count as MIN_PARAGRAPHS = 4.
    assert wording.value == pytest.approx(2 / 4)
    assert by_signal["attack_on_reputation"].value == pytest.approx(1 / 4)
    assert [r.root.span.paragraph for r in wording.source_refs] == [1, 0]
    assert "in 2 of 3 paragraphs" in wording.detail
    assert by_signal["attack_on_reputation"].source_refs[0].root.span.end == len(paragraphs[1])
    assert [e.id for e in evidence] == ["s1", "s2"]


def _one_flagged_paragraph(sentence_probs: list[float]):
    """A paragraph of two sentences flagged for loaded language, and per-sentence scores."""
    paragraphs = ["The council met on Monday. These traitors are destroying our city!"]
    probs = np.full((1, len(LABELS)), 0.1, dtype=np.float32)
    probs[0, LABELS.index("Loaded_Language")] = 0.9
    thresholds = np.full(len(LABELS), 0.5, dtype=np.float32)
    column = LABELS.index("Loaded_Language")
    sentences = {0: []}
    for span, p in zip([(0, 26), (27, 67)], sentence_probs, strict=True):
        row = np.full(len(LABELS), 0.05, dtype=np.float32)
        row[column] = p
        sentences[0].append((span, row))
    return paragraphs, probs, thresholds, sentences


def test_a_technique_points_at_the_sentence_that_carries_it() -> None:
    paragraphs, probs, thresholds, sentences = _one_flagged_paragraph([0.1, 0.8])
    [item] = technique_evidence(paragraphs, [0], probs, LABELS, thresholds, ids(), sentences)
    span = item.source_refs[0].root.span
    assert paragraphs[0][span.start : span.end] == "These traitors are destroying our city!"
    # Detection and value stay per paragraph: the fitted weights still apply.
    assert item.value == pytest.approx(1 / 4)


def test_no_sentence_near_the_threshold_keeps_the_whole_paragraph() -> None:
    # 0.2 is under half of the 0.5 threshold: the technique only shows across sentences.
    paragraphs, probs, thresholds, sentences = _one_flagged_paragraph([0.2, 0.15])
    [item] = technique_evidence(paragraphs, [0], probs, LABELS, thresholds, ids(), sentences)
    span = item.source_refs[0].root.span
    assert (span.start, span.end) == (0, len(paragraphs[0]))


def test_technique_share_of_a_long_and_of_a_capped_text() -> None:
    paragraphs = [f"Paragraph number {i} of the report." for i in range(12)]
    probs = np.full((10, len(LABELS)), 0.1, dtype=np.float32)
    probs[3, LABELS.index("Doubt")] = 0.93  # one chance hit in a long report
    thresholds = np.full(len(LABELS), 0.5, dtype=np.float32)
    [item] = technique_evidence(paragraphs, list(range(10)), probs, LABELS, thresholds, ids())
    assert item.value == pytest.approx(0.1)
    assert "in 1 of the first 10 paragraphs" in item.detail


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
