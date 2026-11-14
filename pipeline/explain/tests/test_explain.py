"""The explain stage keeps only what the API would keep, and never calls the LLM for nothing."""

import asyncio
import json

import pytest

from pipeline import explain
from pipeline.common.fixtures import example_analysis
from pipeline.explain import Draft, check, digest, quotations


def draft(summary: str, *reasons: tuple[str, list[str]]) -> Draft:
    return Draft.model_validate(
        {"summary": summary, "reasons": [{"text": t, "evidence_ids": i} for t, i in reasons]}
    )


def test_quotations_follow_the_api_rule() -> None:
    text = 'He said "short one" and “The government will ban private wells by January.” and «ok»'
    assert quotations(text) == ["The government will ban private wells by January"]
    assert quotations("„Die Regierung verbietet Brunnen“ und »Brunnen sind frei«") == [
        "Die Regierung verbietet Brunnen",
        "Brunnen sind frei",
    ]


def test_reasons_need_known_evidence_and_verbatim_quotes() -> None:
    analysis = example_analysis()
    result = check(
        analysis,
        draft(
            "Charged language and a claim rated false.",
            ("Unknown IDs are removed, known kept.", ["s4", "nope", "s4"]),
            ("No valid evidence at all.", ["nope"]),
            ("Misquotes: “The government will forbid all wells tomorrow”.", ["s1"]),
            ("Quotes verbatim: “Only a traitor would defend this shameful plan”.", ["s1"]),
            ("Two sites copied it.", ["c1"]),
            ("A fourth reason is one too many.", ["c2"]),
        ),
    )
    assert [(r.text[:12], r.evidence_ids) for r in result.reasons] == [
        ("Unknown IDs ", ["s4"]),
        ("Quotes verba", ["s1"]),
        ("Two sites co", ["c1"]),
    ]
    assert result.summary == "Charged language and a claim rated false."


def test_misquoting_summary_is_blanked() -> None:
    result = check(example_analysis(), draft('It says "wells will be banned next week by law".'))
    assert result.summary == ""


def test_digest_carries_scores_and_strongest_evidence_first() -> None:
    payload = json.loads(digest(example_analysis()))
    assert payload["scores"]["single"]["confidence"] == 0.86
    ids = [e["id"] for e in payload["evidence"]]
    assert ids[0] == "s4"  # rated false: strength 1.0
    assert set(ids) == {e.id for e in example_analysis().evidence}
    assert payload["claims"][0] == "The government will ban private wells by January"


def test_run_sends_evidence_as_user_content(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, str] = {}

    async def fake_ask(schema: type, *, system: str, user: str, **_: object) -> Draft:
        sent["system"], sent["user"] = system, user
        return draft("Summary.", ("A fact-checker rated the claim False.", ["s4"]))

    monkeypatch.setattr(explain.llm, "ask_json_async", fake_ask)
    patch = asyncio.run(explain.run(example_analysis()))
    assert "G-TRUTH12345" in sent["user"] and "G-TRUTH12345" not in sent["system"]
    assert patch.explanation.reasons[0].evidence_ids == ["s4"]


def test_no_evidence_no_llm_call(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail(*_: object, **__: object) -> Draft:
        raise AssertionError("the LLM must not be called")

    monkeypatch.setattr(explain.llm, "ask_json_async", fail)
    analysis = example_analysis()
    analysis.evidence = []
    assert analysis.scores is not None
    analysis.scores.coordinated.abstained = True
    analysis.scores.coordinated.confidence = None
    analysis.scores.coordinated.reason = "Only 1 other item was found online."
    explanation = asyncio.run(explain.run(analysis)).explanation
    assert explanation.reasons == []
    assert "coordinated: Only 1 other item was found online." in explanation.summary


def _run_with(monkeypatch: pytest.MonkeyPatch, analysis, summary: str) -> str:
    async def fake_ask(*_: object, **__: object) -> Draft:
        return draft(summary, ("A fact-checker rated the claim False.", ["s4"]))

    monkeypatch.setattr(explain.llm, "ask_json_async", fake_ask)
    return asyncio.run(explain.run(analysis)).explanation.summary


def test_prior_confidences_are_disclosed_whatever_the_model_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert not explain.WEIGHTS.single.calibrated  # committed weights are still priors
    payload = json.loads(digest(example_analysis()))
    assert payload["scores"]["single"]["calibrated"] is False
    summary = _run_with(monkeypatch, example_analysis(), "Single-actor signs: 86%.")
    assert summary == f"Single-actor signs: 86%. {explain.PRIORS_NOTE}"
    # A misquoting summary is blanked; the note still stands alone.
    blanked = _run_with(
        monkeypatch, example_analysis(), 'It says "this text is not in the record".'
    )
    assert blanked == explain.PRIORS_NOTE


def test_no_note_when_nothing_uncalibrated_is_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    analysis = example_analysis()
    assert analysis.scores is not None
    for score in (analysis.scores.single, analysis.scores.coordinated):
        score.abstained, score.confidence, score.reason = True, None, "Too little coverage."
    assert _run_with(monkeypatch, analysis, "Both dimensions abstained.") == (
        "Both dimensions abstained."
    )
    fitted = explain.WEIGHTS.single.model_copy(update={"n": 120})
    coordinated = explain.WEIGHTS.coordinated.model_copy(update={"n": 60})
    monkeypatch.setattr(
        explain,
        "WEIGHTS",
        explain.WEIGHTS.model_copy(update={"single": fitted, "coordinated": coordinated}),
    )
    assert _run_with(monkeypatch, example_analysis(), "Signs: 86%.") == "Signs: 86%."
