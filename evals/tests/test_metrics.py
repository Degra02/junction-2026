from pathlib import Path

import pytest
from propaganda_eval.labelled import LabelledItem, load_labelled
from propaganda_eval.metrics import Prediction, _wilson, evaluate


def item(id_: str, set_name: str, single: bool) -> LabelledItem:
    return LabelledItem(
        id=id_,
        text="text",
        language="en",
        labels={"single": single, "coordinated": False},
        set_name=set_name,
    )


def test_wilson_interval_matches_reference_values():
    assert [round(x, 3) for x in _wilson(8, 10)] == [0.490, 0.943]
    # Zero false positives out of 20 still leaves an upper bound well above zero.
    assert [round(x, 3) for x in _wilson(0, 20)] == [0.0, 0.161]


def test_hard_negative_fpr_counts_only_that_set_and_skips_abstentions():
    items = [
        item("p1", "fact_checker_debunk", True),
        item("s1", "hard_satire", False),
        item("s2", "hard_satire", False),
        item("s3", "hard_satire", False),
        item("w1", "hard_wire_copy", False),
    ]
    predictions = {
        "p1": Prediction("p1", {"single": 0.9, "coordinated": 0.1}),
        "s1": Prediction("s1", {"single": 0.8, "coordinated": 0.1}),  # false positive
        "s2": Prediction("s2", {"single": 0.2, "coordinated": 0.1}),
        "s3": Prediction("s3", {"single": None, "coordinated": None}),  # abstained
        "w1": Prediction("w1", {"single": 0.1, "coordinated": 0.1}),
    }
    single = evaluate(items, predictions).dimensions["single"]

    satire = single.per_set["hard_satire"]
    assert (satire.fp, satire.tn, satire.abstained) == (1, 1, 1)
    assert satire.fpr == 0.5
    assert single.per_set["hard_wire_copy"].fpr == 0.0
    assert (single.overall.tp, single.overall.fp, single.overall.tn) == (1, 1, 2)
    assert single.overall.abstain_rate == pytest.approx(1 / 5)


def test_a_non_boolean_label_is_rejected(tmp_path: Path):
    path = tmp_path / "labelled.jsonl"
    path.write_text(
        '{"id": "x", "text": "t", "labels": {"single": 1, "coordinated": false}, '
        '"set": "mainstream"}\n'
    )
    with pytest.raises(ValueError, match="must be bool"):
        load_labelled(path)


def test_the_committed_seed_set_is_valid():
    items = load_labelled(Path(__file__).resolve().parents[1] / "labelled.jsonl")
    assert len({i.id for i in items}) == len(items)
