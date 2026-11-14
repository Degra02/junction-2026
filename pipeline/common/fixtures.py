"""The example analysis every stage can be tested against, without the other stages.

`contracts/fixtures/analysis.json` is one finished `Analysis` of an invented article (a wire
report, two copies on sites sharing an analytics ID, a fact-check, an unrelated item). A test
in `contracts/` replays it through the API's validation, so it always matches the contract.
It ships with the repository, not with the worker image: use it in tests only.

    def test_story_keeps_the_copies():
        analysis = example_analysis()
        patch = run(analysis)   # a stage ignores the fields of the stages after it
"""

from pathlib import Path

from pipeline.common.contracts import Analysis

FIXTURE = Path(__file__).resolve().parents[2] / "contracts" / "fixtures" / "analysis.json"


def example_analysis() -> Analysis:
    """A fresh copy of the example analysis; change it freely."""
    return Analysis.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
