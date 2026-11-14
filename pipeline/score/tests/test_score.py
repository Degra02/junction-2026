"""The score stage on the example analysis, and the combiner fit on synthetic labels."""

import json
from pathlib import Path

import numpy as np
import pytest

from pipeline.common.contracts import Evidence, Family, LanguageSupport, UrlRef
from pipeline.common.fixtures import example_analysis
from pipeline.score import SUPPORTED_CAP, WEIGHTS, run
from pipeline.score.families import COORDINATED, SINGLE, family_values
from pipeline.score.fit import ablation, fit_logistic, main


def evidence(eid: str, family: Family, signal: str, value: float) -> Evidence:
    return Evidence(
        id=eid,
        family=family,
        signal=signal,
        value=value,
        detail="x",
        source_refs=[UrlRef(kind="url", url="https://example.org")],
    )


def test_example_scores_both_dimensions_with_valid_breakdown() -> None:
    analysis = example_analysis()
    scores = run(analysis).scores
    ids = {e.id: e.family for e in analysis.evidence}
    for score, families in ((scores.single, SINGLE), (scores.coordinated, COORDINATED)):
        assert not score.abstained and score.reason is None
        assert score.confidence is not None and 0.5 < score.confidence <= 1.0
        assert [b.family for b in score.breakdown] == list(families)
        for entry in score.breakdown:
            assert all(ids[e] == entry.family for e in entry.evidence_ids)
    known = next(b for b in scores.coordinated.breakdown if b.family == Family.known_networks)
    assert (known.contribution, known.evidence_ids) == (0.0, [])


def test_only_the_strongest_signal_of_a_family_counts() -> None:
    items = [
        evidence("s1", Family.techniques, "manipulative_wording", 0.45),
        evidence("s2", Family.techniques, "attack_on_reputation", 0.3),
        evidence("s3", Family.source_profile, "domain_age_days", 4000),
        evidence("s4", Family.source_profile, "outlet_wire_service", 1.0),
        evidence("s5", Family.techniques, "a_signal_nobody_mapped", 1.0),
    ]
    values = {v.family: v for v in family_values(items, SINGLE)}
    assert values[Family.techniques].value == pytest.approx(0.9)
    assert values[Family.techniques].evidence_ids == ["s1", "s2"]
    assert values[Family.source_profile].value == pytest.approx(-0.5)
    assert values[Family.source_profile].evidence_ids == ["s4", "s3"]
    assert values[Family.tone].value == 0.0


def test_few_related_reports_abstain_single_unless_fact_checked() -> None:
    analysis = example_analysis()
    analysis.context = [c for c in analysis.context if c.id in {"ctx1", "ctx4"}]
    analysis.evidence = [e for e in analysis.evidence if e.family != Family.fact_checks]
    single = run(analysis).scores.single
    assert single.abstained and single.confidence is None
    assert single.reason is not None and "Only 1 other report" in single.reason
    assert single.breakdown  # still shown behind "how we calculated this"


def test_coordinated_abstains_without_copies_and_little_context() -> None:
    analysis = example_analysis()
    analysis.context = analysis.context[:1]
    analysis.evidence = [e for e in analysis.evidence if e.family in SINGLE]
    coordinated = run(analysis).scores.coordinated
    assert coordinated.abstained and "too few to look for copies" in (coordinated.reason or "")


def test_copies_are_enough_for_coordinated_even_with_little_context() -> None:
    analysis = example_analysis()
    analysis.context = analysis.context[:2]
    assert not run(analysis).scores.coordinated.abstained


def test_strong_evidence_both_ways_abstains() -> None:
    analysis = example_analysis()
    analysis.evidence.append(evidence("s9", Family.source_profile, "outlet_fact_checker", 1.0))
    analysis.evidence = [e for e in analysis.evidence if e.id != "s5"]
    single = run(analysis).scores.single
    assert single.abstained and "points both ways" in (single.reason or "")


def test_unsupported_language_abstains_and_supported_is_capped() -> None:
    analysis = example_analysis()
    assert analysis.language is not None
    analysis.language.support = LanguageSupport.unsupported
    scores = run(analysis).scores
    assert scores.single.abstained and scores.coordinated.abstained
    analysis.language.support = LanguageSupport.supported
    assert run(analysis).scores.single.confidence == SUPPORTED_CAP


def test_fit_recovers_the_direction_of_the_signal() -> None:
    rng = np.random.default_rng(1)
    x = rng.uniform(-1, 1, size=(400, 2))
    y = (rng.uniform(size=400) < 1 / (1 + np.exp(-(0.5 + 3 * x[:, 0])))).astype(float)
    intercept, coefficients = fit_logistic(x, y, l2=0.0)
    assert coefficients[0] == pytest.approx(3, abs=0.8)
    assert abs(coefficients[1]) < 0.6
    assert intercept == pytest.approx(0.5, abs=0.4)


def test_ablation_shows_which_family_carries_the_signal() -> None:
    rng = np.random.default_rng(2)
    x = rng.uniform(-1, 1, size=(300, 3))
    x[:, 2] = 0.0  # a family that never fired is left out of the report
    y = (rng.uniform(size=300) < 1 / (1 + np.exp(-4 * x[:, 0]))).astype(float)
    report = ablation(x, y, (Family.techniques, Family.tone, Family.claim_support), folds=5)
    assert set(report) == {"techniques", "tone"}
    informative, noise = report["techniques"], report["tone"]
    assert informative["items_nonzero"] == 300
    assert informative["auc_alone"] > 0.8 and informative["auc_without"] < 0.6
    assert noise["auc_alone"] < 0.6 and noise["auc_without"] > 0.8


def test_fit_cli_reports_without_writing(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    lines = []
    for label in (1, 1, 0, 0, 1, 0):
        analysis = example_analysis()
        if not label:
            analysis.evidence = []
        lines.append(
            json.dumps(
                {"analysis": analysis.model_dump(mode="json"), "single": label, "coordinated": None}
            )
        )
    # An item on which the dimension abstains (no coverage found) is counted, not fitted.
    unseen = example_analysis()
    unseen.context, unseen.evidence = [], []
    lines.append(
        json.dumps({"analysis": unseen.model_dump(mode="json"), "single": 1, "coordinated": None})
    )
    path = tmp_path / "labelled.jsonl"
    path.write_text("\n".join(lines))
    before = WEIGHTS.model_dump()
    main([str(path), "--dry-run"])
    out = capsys.readouterr().out
    assert "single: 3 positive and 3 negative scored items; 1 abstained and left out" in out
    assert '"n": 6' in out and '"auc": 1.0' in out
    assert '"folds": 3' in out and '"ablation"' in out
    # Positives carry all the fixture's evidence and negatives none: every family separates.
    assert "single: WARNING fact_checks alone separates the classes (AUC 1.0)" in out
    assert "coordinated: not enough labels" in out
    assert WEIGHTS.model_dump() == before


@pytest.mark.parametrize(
    ("signal", "value", "expected"),
    [
        ("contradicted", 5 / 6, 2 / 3),  # 4 of 4 addressing sources contradict the claim
        ("contradicted", 0.5, 0.0),  # split
        ("contradicted", 0.2, -0.6),  # 0 of 3: corroborated, points away, never below -0.6
        ("tone_vs_peers", 3.0, 1.0),
        ("tone_vs_peers", -6.0, -0.5),  # calmer than the peers: weaker evidence
    ],
)
def test_corroboration_and_calm_tone_point_away(signal: str, value: float, expected: float) -> None:
    family = Family.claim_support if signal == "contradicted" else Family.tone
    [found] = [
        v
        for v in family_values([evidence("s1", family, signal, value)], SINGLE)
        if v.family == family
    ]
    assert found.value == pytest.approx(expected)
