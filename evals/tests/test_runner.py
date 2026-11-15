import json
from pathlib import Path

from propaganda_eval.labelled import LabelledItem
from propaganda_eval.runner import Outcome, failure, fit_row, prediction, rescore

from pipeline.common.contracts import Analysis, AnalysisStatus, StepState
from pipeline.score import run as score

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "analysis_positive.json"


def analysis() -> Analysis:
    return Analysis.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


ITEM = LabelledItem(
    id="v1",
    url="https://example.org/a",
    language="en",
    labels={"single": None, "coordinated": True},
    set_name="viginum_pravda",
)


def test_a_finished_analysis_with_a_failed_step_counts_as_a_failure():
    a = analysis()
    assert a.status == AnalysisStatus.done and failure(a) is None
    a.steps[0].state = StepState.failed
    a.steps[0].error = "the stage failed (TimeoutError)"
    row = prediction(ITEM, Outcome(ITEM, a, failure(a)))
    assert row["failed"] is True
    assert "TimeoutError" in row["error"]


def test_ablation_rescores_without_each_present_family():
    a = analysis()
    row = prediction(ITEM, Outcome(ITEM, a, None))
    present = {e.family.value for e in a.evidence}
    assert {f for dim in row["ablation"].values() for f in dim} == present
    rescored = score(a).scores
    for dim, families in row["ablation"].items():
        full = getattr(rescored, dim).confidence
        for family, confidence in families.items():
            # Every family in the fixture points toward propaganda: removing one never raises it.
            if full is not None and confidence is not None:
                assert confidence <= full, (dim, family)


def test_rescore_replaces_the_stored_scores_with_this_checkouts(tmp_path: Path):
    a = analysis()
    stored = a.model_copy(update={"scores": None})  # what the run saw does not matter
    fit = tmp_path / "fit.jsonl"
    fit.write_text(json.dumps(fit_row(ITEM, stored)) + "\n", encoding="utf-8")
    out = tmp_path / "predictions.jsonl"
    assert rescore([fit], out) == 1
    row = json.loads(out.read_text(encoding="utf-8"))
    expected = score(a).scores
    assert row["item_id"] == ITEM.id and row["failed"] is False
    assert row["scores"] == {
        "single": expected.single.confidence,
        "coordinated": expected.coordinated.confidence,
    }
