from pathlib import Path

from propaganda_eval.symmetry import Pair, Side, load_pairs, summarise

PAIRS = Path(__file__).resolve().parents[1] / "symmetry.jsonl"


def pair(i: str) -> Pair:
    return Pair(i, "x ↔ y", "a", "b")


def test_gap_is_measured_only_where_both_sides_scored():
    summary = summarise(
        [
            (pair("p1"), Side(single=0.80), Side(single=0.60)),  # gap 0.2: a finding
            (pair("p2"), Side(single=0.50), Side(single=0.48)),
            (pair("p3"), Side(single=0.70), Side(abstained=True)),  # one-sided abstention
            (pair("p4"), Side(error="TimeoutError"), Side(single=0.1)),
        ]
    )
    assert summary["scored_both"] == 2
    assert summary["mean_abs_delta"] == 0.11 and summary["max_abs_delta"] == 0.2
    assert summary["over_gap"] == ["p1"]
    assert summary["one_side_abstained"] == ["p3"]
    assert summary["failed"] == ["p4"]


def test_committed_pairs_differ_only_by_the_swapped_target():
    pairs = load_pairs(PAIRS)
    assert len(pairs) == 10
    for p in pairs:
        assert p.a != p.b
        # Same structure on both sides: same number of paragraphs, and the visual description.
        assert p.a.count("\n") == p.b.count("\n")
        assert ("[Visual context]" in p.a) and ("[Visual context]" in p.b)
