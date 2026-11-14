import json
from pathlib import Path

import pytest
from propaganda_eval.labelled import LabelledItem, load_labelled
from propaganda_eval.metrics import Prediction, _wilson, evaluate, to_json


def item(
    id_: str, set_name: str, single: bool | None, coordinated: bool | None = False
) -> LabelledItem:
    return LabelledItem(
        id=id_,
        text="a secret sentence that must not leak",
        url=f"https://example.org/{id_}",
        language="en",
        labels={"single": single, "coordinated": coordinated},
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


def test_failures_are_not_abstentions_and_null_labels_are_left_out():
    items = [
        item("p1", "fact_checker_debunk", True, None),
        item("p2", "fact_checker_debunk", True, None),
        item("n1", "mainstream", False),
        item("n2", "mainstream", False),
    ]
    predictions = {
        "p1": Prediction("p1", {"single": 0.9, "coordinated": 0.9}),
        "p2": Prediction("p2", {}, failed=True),
        "n1": Prediction("n1", {"single": None, "coordinated": 0.1}),
    }
    result = evaluate(items, predictions).dimensions

    single = result["single"].overall
    assert (single.tp, single.abstained, single.failed) == (1, 1, 1)
    assert single.abstain_rate == pytest.approx(1 / 2)  # of the 2 analyses that finished
    assert single.failure_rate == pytest.approx(1 / 3)
    assert result["single"].missing == 1
    # p1 and p2 have no coordinated label: p1's 0.9 is not a false positive.
    coordinated = result["coordinated"].overall
    assert (coordinated.fp, coordinated.tn, coordinated.failed) == (0, 1, 0)


def test_ablation_shows_what_removing_a_family_costs():
    items = [item("v1", "viginum_pravda", None, True), item("w1", "hard_wire_copy", False)]
    predictions = {
        "v1": Prediction(
            "v1",
            {"single": 0.2, "coordinated": 0.9},
            ablation={"coordinated": {"known_networks": 0.3, "text_reuse": 0.8}},
        ),
        "w1": Prediction("w1", {"single": 0.1, "coordinated": 0.1}),
    }
    coordinated = evaluate(items, predictions).dimensions["coordinated"]
    assert coordinated.overall.recall == 1.0
    assert coordinated.ablation["known_networks"].recall == 0.0
    assert coordinated.ablation["text_reuse"].recall == 1.0


def test_metrics_json_has_numbers_but_no_item_content():
    items = [item("p1", "fact_checker_debunk", True), item("n1", "hard_satire", False)]
    predictions = {
        "p1": Prediction("p1", {"single": 0.9, "coordinated": 0.1}),
        "n1": Prediction("n1", {"single": 0.7, "coordinated": 0.1}),
    }
    data = to_json(evaluate(items, predictions))
    text = json.dumps(data)
    assert "secret sentence" not in text and "example.org" not in text
    assert data["dimensions"]["single"]["per_set"]["hard_satire"]["fpr"] == 1.0


def test_labels_must_be_bool_or_null(tmp_path: Path):
    path = tmp_path / "labelled.jsonl"
    path.write_text(
        '{"id": "x", "url": "https://a.example/x", "labels": {"single": 1, "coordinated": null}, '
        '"set": "mainstream"}\n'
    )
    with pytest.raises(ValueError, match="must be true, false or null"):
        load_labelled(path)


def test_an_article_body_is_rejected(tmp_path: Path):
    path = tmp_path / "labelled.jsonl"
    row = {
        "id": "x",
        "text": "word " * 200,
        "labels": {"single": True, "coordinated": None},
        "set": "fact_checker_debunk",
    }
    path.write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="commit the url"):
        load_labelled(path)


def test_the_committed_set_is_valid():
    items = load_labelled(Path(__file__).resolve().parents[1] / "labelled.jsonl")
    assert items
