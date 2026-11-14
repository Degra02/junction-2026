import json
from pathlib import Path

import pytest

from pipeline.common.contracts import Analysis
from pipeline.score.families import STRENGTH

FIXTURES = sorted((Path(__file__).resolve().parents[1] / "fixtures").glob("*.json"))


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_fixture_is_a_valid_analysis_with_scored_signals(path: Path):
    analysis = Analysis.model_validate(json.loads(path.read_text(encoding="utf-8")))
    # A signal name the combiner does not map is silently ignored by scoring.
    unknown = [
        f"{e.family.value}/{e.signal}"
        for e in analysis.evidence
        if (e.family, e.signal) not in STRENGTH
    ]
    assert unknown == []
