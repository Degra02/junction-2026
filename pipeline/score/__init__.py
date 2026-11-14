"""Stage 6, score: one calibrated confidence per dimension, or an abstention (plan §5).

For each dimension (single-actor, coordinated):

1. `families.family_values` turns the evidence into one value per family in `[-1, 1]`
   (strongest signal only).
2. A logistic regression combines them: `confidence = sigmoid(intercept + Σ coef_f × value_f)`.
   Coefficients live in `weights.json`; `python -m pipeline.score.fit` refits them on the
   labelled set (cross-validated). Until then they are hand-set priors (`weights.json` says
   which in `source`).
3. `breakdown` lists every family of the dimension with its contribution `coef_f × value_f`
   (log-odds, the weights shown to the user) and its evidence IDs, strongest first.

Abstains ("Not enough evidence", no confidence) when the language is unsupported, when the
source is a satire publication (single-actor), when too little context was found, or when strong
evidence points both ways. For languages that are supported but not evaluated the confidence is
capped at SUPPORTED_CAP (D2).
"""

import json
import math
from pathlib import Path

from pydantic import BaseModel

from pipeline.common.contracts import (
    Analysis,
    Contribution,
    Family,
    LanguageSupport,
    OutletType,
    Score,
    ScorePatch,
    Scores,
)
from pipeline.score.families import COORDINATED, SINGLE, FamilyValue, family_values

WEIGHTS_FILE = Path(__file__).with_name("weights.json")
MIN_RELATED = 3
SUPPORTED_CAP = 0.85
# Families this strong in opposite directions make the result an abstention.
DISAGREEMENT = 0.7


class DimensionWeights(BaseModel):
    intercept: float
    coefficients: dict[Family, float]
    # Labelled items the weights were fitted on (0 for priors) and cross-validation metrics.
    n: int = 0
    cv: dict[str, object] | None = None

    @property
    def calibrated(self) -> bool:
        """Fitted on labelled data (`pipeline.score.fit`), not hand-set priors."""
        return self.n > 0


class Weights(BaseModel):
    source: str
    single: DimensionWeights
    coordinated: DimensionWeights


WEIGHTS = Weights.model_validate_json(WEIGHTS_FILE.read_text(encoding="utf-8"))


def run(analysis: Analysis) -> ScorePatch:
    single = family_values(analysis.evidence, SINGLE)
    coordinated = family_values(analysis.evidence, COORDINATED)
    return ScorePatch(
        scores=Scores(
            single=score(single, WEIGHTS.single, analysis, _single_abstention(analysis, single)),
            coordinated=score(
                coordinated,
                WEIGHTS.coordinated,
                analysis,
                _coordinated_abstention(analysis, coordinated),
            ),
        )
    )


def confidence(values: list[FamilyValue], weights: DimensionWeights) -> float:
    logit = weights.intercept + sum(
        weights.coefficients.get(v.family, 0.0) * v.value for v in values
    )
    return 1.0 / (1.0 + math.exp(-logit))


def score(
    values: list[FamilyValue],
    weights: DimensionWeights,
    analysis: Analysis,
    abstention: str | None,
) -> Score:
    breakdown = [
        Contribution(
            family=v.family,
            contribution=round(weights.coefficients.get(v.family, 0.0) * v.value, 3),
            evidence_ids=v.evidence_ids,
        )
        for v in values
    ]
    if abstention is None:
        abstention = _disagreement(values)
    if abstention is not None:
        return Score(confidence=None, abstained=True, reason=abstention, breakdown=breakdown)
    value = confidence(values, weights)
    if analysis.language is not None and analysis.language.support == LanguageSupport.supported:
        value = min(value, SUPPORTED_CAP)
    return Score(confidence=round(value, 3), abstained=False, reason=None, breakdown=breakdown)


def _common_abstention(analysis: Analysis) -> str | None:
    if analysis.document is None or not any(p.strip() for p in analysis.document.paragraphs):
        return "No text was analysed."
    if analysis.language is not None and analysis.language.support == LanguageSupport.unsupported:
        return "The language of this text is not supported yet."
    return None


def _is_satire(analysis: Analysis) -> bool:
    outlet = analysis.document.outlet if analysis.document else None
    if outlet and any(
        s.domain == outlet and s.outlet_type == OutletType.satire for s in analysis.sources
    ):
        return True
    return any(
        e.family == Family.source_profile and e.signal == "outlet_satire" for e in analysis.evidence
    )


def _single_abstention(analysis: Analysis, values: list[FamilyValue]) -> str | None:
    if reason := _common_abstention(analysis):
        return reason
    if _is_satire(analysis):
        return "The source is a satire publication, not factual news reporting."
    if analysis.document and any(
        p.startswith("[Satire/humour meme] ") for p in analysis.document.paragraphs
    ):
        return "This image appears to be humour or satire without checkable factual claims."
    fact_checked = any(v.family == Family.fact_checks and v.value != 0 for v in values)
    satire_domains = {s.domain for s in analysis.sources if s.outlet_type == OutletType.satire}
    related = [
        c
        for c in analysis.context
        if c.in_story is not False and c.fact_check is None and c.outlet not in satire_domains
    ]
    if not fact_checked and len(related) < MIN_RELATED:
        return (
            f"Only {len(related)} other report{'s' if len(related) != 1 else ''} on the same "
            f"event {'was' if len(related) == 1 else 'were'} found; at least {MIN_RELATED} are "
            "needed to compare."
        )
    return None


def _coordinated_abstention(analysis: Analysis, values: list[FamilyValue]) -> str | None:
    if reason := _common_abstention(analysis):
        return reason
    # Copies or a listed domain are evidence on their own, however little else was found.
    if any(v.value > 0 for v in values if v.family in (Family.text_reuse, Family.known_networks)):
        return None
    found = [c for c in analysis.context if c.fact_check is None]
    if len(found) < MIN_RELATED:
        return (
            f"Only {len(found)} other item{'s' if len(found) != 1 else ''} "
            f"{'was' if len(found) == 1 else 'were'} found online, too few to look for copies."
        )
    return None


def _disagreement(values: list[FamilyValue]) -> str | None:
    up = [v.family.value.replace("_", " ") for v in values if v.value >= DISAGREEMENT]
    down = [v.family.value.replace("_", " ") for v in values if v.value <= -DISAGREEMENT]
    if up and down:
        return (
            f"The evidence points both ways: {', '.join(up)} against, {', '.join(down)} in "
            "favour of the content."
        )
    return None


def save_weights(weights: Weights) -> None:
    """Write `weights` to `weights.json` (used by `pipeline.score.fit`)."""
    WEIGHTS_FILE.write_text(
        json.dumps(weights.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
